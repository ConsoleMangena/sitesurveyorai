"""
SiteSurveyor AI — Unified Cloud API & MCP Server (Render / Production)
======================================================================
Dual-protocol service for cloud deployment on Render:
1. REST API: For direct calls from web apps, Supabase Edge Functions (Deno),
   and dashboard frontends (JSON endpoints + static output artifact serving).
2. MCP Server (SSE): Model Context Protocol endpoint for autonomous AI agents
   (OpenClaw, Claude Desktop, Cursor, remote LLM orchestrators).

Long surveys: POST /api/survey with ``async_mode=true`` returns a job id and the browser
polls /api/jobs/{id}. A survey takes minutes, so holding the HTTP request open means a
proxy or browser timeout can discard work that already finished. The synchronous default
is kept for scripted callers that can afford to wait.

Usage:
    uvicorn src.api:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Always import config first to configure PROJ paths before rasterio loads
import src.config as cfg
from src.mcp.server import (
    _SITE_LOCK,
    get_boreholes as _mcp_get_boreholes,
    get_executive_dossier as _mcp_get_executive_dossier,
    get_hazard_safety as _mcp_get_hazard_safety,
    get_minerals as _mcp_get_minerals,
    get_soil_capability as _mcp_get_soil_capability,
    mcp,
    set_progress_callback,
    survey_site as _mcp_survey_site,
)

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import Response
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------
class SurveyRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90, description="Target latitude in decimal degrees")
    longitude: float = Field(..., ge=-180, le=180, description="Target longitude in decimal degrees")
    categories: list[str] = Field(default=["all"], description="Categories: 'water', 'minerals', 'soil', 'hazard', or 'all'")
    client_name: str = Field(default="Client", max_length=120, description="Client or project name")
    address: str = Field(default="", max_length=240, description="Location or property address description")
    half_deg: float = Field(default=0.12, gt=0, le=0.5, description="AOI radius buffer in degrees (~13.3 km)")
    async_mode: bool = Field(
        default=False,
        description="Return a job id immediately and let the caller poll /api/jobs/{id} "
                    "instead of holding the request open for a multi-minute survey.",
    )


class TargetRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90, description="Target latitude in decimal degrees")
    longitude: float = Field(..., ge=-180, le=180, description="Target longitude in decimal degrees")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of ranked candidates to return")
    half_deg: float = Field(default=0.12, gt=0, le=0.5, description="AOI radius buffer in degrees (~13.3 km)")


# ---------------------------------------------------------------------------
# FastAPI App Initialization
# ---------------------------------------------------------------------------
app = FastAPI(
    title="SiteSurveyor AI — Cloud Geospatial Intelligence Engine",
    description="Autonomous multi-criteria satellite screening API & Model Context Protocol (MCP) server by Eineva Labs.",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

logger = logging.getLogger("sitesurveyor.api")

# The Digital Earth Africa WCS envelope. Outside it the honest answer is "no data",
# not a survey built from a raster that failed to warp.
COVERAGE_LON = (-30.0, 66.0)
COVERAGE_LAT = (-56.0, 41.0)

# Surveys are single-flight per process, so a job can sit queued behind another one.
# Six hours is long enough for a browser to come back to it and short enough that the
# store cannot grow without bound on a long-lived instance.
JOB_TTL_SECONDS = 6 * 60 * 60

# Artifact names the survey produces. Only files that actually exist are advertised:
# a download link that 404s reads as a broken product, not as a partial run.
DELIVERABLES = {
    "html_report": "SiteSurveyor_Intelligence_Report.html",
    "master_json_dossier": "master_site_dossier.json",
    "boreholes_kmz": "candidate_borehole_sites.kmz",
    "minerals_kmz": "candidate_mineral_targets.kmz",
    "soil_kmz": "candidate_land_zones.kmz",
    "safest_sites_kmz": "safest_buildable_sites.kmz",
    "groundwater_map": "groundwater_potential_map.png",
    "minerals_map": "mineral_prospectivity_map.png",
    "soil_map": "soil_capability_map.png",
    "hazard_map": "hazard_risk_map.png",
}

CLAIM_CEILING = {
    "water": "Prioritisation of investigation sites only. Not a statement of water yield, "
             "borehole success, or aquifer depth until VES/ERT and drilling confirm it.",
    "minerals": "Prioritisation of exploration targets only. Not a statement of mineral grade, "
                "tonnage, or economic viability until assay and mapping confirm it.",
    "soil": "Screening-level land capability proxy only. Not a soil classification or a "
            "fertiliser/irrigation recommendation until laboratory analysis.",
    "hazard": "Screening-level hazard exposure proxy only. Not a design-event flood level, "
              "slope-stability calculation, or geotechnical sign-off.",
    "survey": "Prioritisation of investigation sites only. Not a statement of water yield, "
              "mineral grade, or buildability. Ground truthing is required before capital spend.",
}


# ---------------------------------------------------------------------------
# CORS policy
# ---------------------------------------------------------------------------
def _allowed_origins() -> list[str]:
    """Cross-origin callers, opt-in.

    The bundled sandbox fetches /api/* with relative URLs, so it is same-origin and needs
    no entry. A wildcard combined with allow_credentials=True makes Starlette reflect
    whatever Origin header arrives, which lets any website make credentialed calls here
    and read the responses -- so there is no wildcard mode, only a list.
    """
    raw = os.getenv("ALLOWED_ORIGINS", "")
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    if "*" in origins:
        logger.warning("ALLOWED_ORIGINS contains '*' but credentialed CORS cannot be "
                       "wildcarded; ignoring the wildcard. List explicit origins instead.")
        origins = [o for o in origins if o != "*"]
    for origin in origins:
        if not origin.startswith(("https://", "http://localhost", "http://127.0.0.1")):
            logger.warning("ALLOWED_ORIGINS entry %r is not https and not localhost -- "
                           "a plain-HTTP origin lets a network observer read API responses.", origin)
    return origins


def _is_same_origin(origin: str, host: str | None) -> bool:
    """True when a page is calling the very host it was served from.

    Compared against the request Host rather than a configured port, so the bundled
    sandbox works on whatever port the process happens to bind.
    """
    if not host:
        return False
    origin_host = urlsplit(origin).netloc
    return bool(origin_host) and origin_host.lower() == host.lower()


_origins = _allowed_origins()
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info("CORS enabled for %d origin(s): %s", len(_origins), ", ".join(_origins))
else:
    logger.info("CORS disabled: no ALLOWED_ORIGINS set. Same-origin clients (the bundled "
                "sandbox) and non-browser MCP agents are unaffected.")


# ---------------------------------------------------------------------------
# Transport middleware
# ---------------------------------------------------------------------------
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "SAMEORIGIN",
    "Permissions-Policy": "geolocation=(self), camera=(), microphone=()",
    # The sandbox is one hand-written page and the dossier is one generated document, so
    # both legitimately need inline style/script. Everything else is restricted to the
    # three CDNs the page actually loads (Leaflet, Google Fonts, Swagger UI).
    "Content-Security-Policy": "; ".join([
        "default-src 'self'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'self'",
        "img-src 'self' data: blob: https://unpkg.com https://*.arcgisonline.com https://*.tile.openstreetmap.org",
        "script-src 'self' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.net",
        "style-src 'self' 'unsafe-inline' https://unpkg.com https://fonts.googleapis.com https://cdn.jsdelivr.net",
        "font-src 'self' data: https://fonts.gstatic.com",
        "connect-src 'self'",
    ]),
}


class _SecurityHeaders:
    """Attach the response headers every browser-facing surface should carry."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in _SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
            await send(message)

        await self.app(scope, receive, send_with_headers)


class _HeadAsGet:
    """Answer HEAD by running the GET route and dropping the body.

    The MCP SSE app is mounted at "" so it can own /sse and /messages/. That mount is
    the last route, so any HEAD request that no route matches falls into it and gets a
    404 from the MCP app -- /health passes a HEAD probe but / and /api/dossier do not,
    which breaks uptime monitors, link checkers and link previews. Routing HEAD as GET
    upstream of the router makes HEAD behave the way HTTP expects.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "HEAD":
            await self.app(scope, receive, send)
            return

        head_scope = {**scope, "method": "GET"}

        async def send_without_body(message):
            if message["type"] == "http.response.body":
                message = {**message, "body": b"", "more_body": False}
            await send(message)

        await self.app(head_scope, receive, send_without_body)


app.add_middleware(_SecurityHeaders)
app.add_middleware(_HeadAsGet)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
def _request_id() -> str:
    return uuid.uuid4().hex[:12]


def _api_error(status_code: int, code: str, message: str, hint: str | None = None) -> HTTPException:
    detail: dict[str, Any] = {"code": code, "message": message}
    if hint:
        detail["hint"] = hint
    return HTTPException(status_code=status_code, detail=detail)


def _internal_error(exc: Exception, request_id: str) -> HTTPException:
    """Log the failure and hand the caller a code they can quote.

    The exception text stays in the server log: it carries absolute paths and upstream
    URLs, which is both an information leak and useless to whoever is looking at a map.
    """
    logger.exception("Request failed (request_id=%s)", request_id)
    return _api_error(
        500,
        "survey_failed",
        "The survey engine failed while processing this request.",
        f"Retry once. If it repeats, quote request id {request_id}.",
    )


def _check_coverage(lat: float, lon: float) -> None:
    if not (COVERAGE_LAT[0] <= lat <= COVERAGE_LAT[1] and COVERAGE_LON[0] <= lon <= COVERAGE_LON[1]):
        raise _api_error(
            400,
            "out_of_coverage",
            f"({lat:.4f}, {lon:.4f}) is outside the Digital Earth Africa coverage envelope.",
            "DE Africa serves roughly 30°W–66°E and 56°S–41°N. Pick a site inside that box; "
            "a survey run outside it would warp empty rasters and report plausible numbers.",
        )


# ---------------------------------------------------------------------------
# Survey execution
# ---------------------------------------------------------------------------
def _target_block(lat: float, lon: float, half_deg: float) -> dict:
    """Describe the AOI without reading the module globals another thread may own."""
    zone = int((lon + 180.0) // 6.0) + 1
    epsg = (32700 + zone) if lat < 0 else (32600 + zone)
    return {
        "latitude": lat,
        "longitude": lon,
        "half_deg": half_deg,
        "cell_m": cfg.CELL,
        "bbox_wgs84": [lon - half_deg, lat - half_deg, lon + half_deg, lat + half_deg],
        "utm_zone": f"{zone}{'S' if lat < 0 else 'N'}",
        "epsg": epsg,
        "crs": f"EPSG:{epsg}",
    }


def _deliverables(base_url: str) -> tuple[dict[str, str], list[str]]:
    urls, missing = {}, []
    for key, filename in DELIVERABLES.items():
        if (cfg.OUT / filename).exists():
            urls[key] = f"{base_url}/outputs/{filename}"
        else:
            missing.append(key)
    return urls, missing


def _run_survey(payload: dict, base_url: str) -> dict:
    """Configure the AOI and run every requested category under the single-site lock.

    ``set_target_site`` mutates module globals that the engines read, so it has to happen
    inside the lock. Doing it in the request handler (before acquiring) let a second
    caller re-point an in-flight survey at a different AOI mid-run.
    """
    lat, lon, half_deg = payload["latitude"], payload["longitude"], payload["half_deg"]
    with _SITE_LOCK:
        cfg.set_target_site(
            lat,
            lon,
            half_deg=half_deg,
            client=payload["client_name"],
            address=payload["address"] or None,
        )
        result = _mcp_survey_site(
            latitude=lat,
            longitude=lon,
            categories=payload["categories"],
            client_name=payload["client_name"],
            address=payload["address"],
            half_deg=half_deg,
        )

    urls, missing = _deliverables(base_url)
    result["target"] = _target_block(lat, lon, half_deg)
    result["download_urls"] = urls
    result["deliverables_missing"] = missing
    return result


# ---------------------------------------------------------------------------
# Job store (persisted to disk in cfg.DATA_DIR / "jobs" + memory cache)
# ---------------------------------------------------------------------------
_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()
JOBS_DIR = cfg.DATA_DIR / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)


def _save_job_to_disk(job: dict) -> None:
    try:
        path = JOBS_DIR / f"{job['id']}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(job, f)
    except Exception as e:
        logger.warning("Could not persist job %s to disk: %s", job.get("id"), e)


def _load_job_from_disk(job_id: str) -> dict | None:
    path = JOBS_DIR / f"{job_id}.json"
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Could not load job %s from disk: %s", job_id, e)
    return None


def _prune_jobs() -> None:
    cutoff = time.time() - JOB_TTL_SECONDS
    with _JOBS_LOCK:
        for job_id in [jid for jid, job in _JOBS.items() if job["submitted_at"] < cutoff]:
            _JOBS.pop(job_id, None)
    try:
        for f in JOBS_DIR.glob("*.json"):
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
    except Exception:
        pass


def _create_job(payload: dict) -> dict:
    _prune_jobs()
    job = {
        "id": uuid.uuid4().hex,
        "status": "queued",
        "stage": "Queued",
        "progress": 0,
        "submitted_at": time.time(),
        "started_at": None,
        "finished_at": None,
        "target": {"latitude": payload["latitude"], "longitude": payload["longitude"]},
        "result": None,
        "error": None,
    }
    with _JOBS_LOCK:
        _JOBS[job["id"]] = job
    _save_job_to_disk(job)
    return job


def _update_job(job_id: str, **fields) -> None:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            job = _load_job_from_disk(job_id)
            if job:
                _JOBS[job_id] = job
        if job is not None:
            job.update(fields)
            _save_job_to_disk(job)


def _job_snapshot(job: dict, include_result: bool = True) -> dict:
    snapshot = {
        "id": job["id"],
        "status": job["status"],
        "stage": job["stage"],
        "progress": job["progress"],
        "submitted_at": job["submitted_at"],
        "started_at": job["started_at"],
        "finished_at": job["finished_at"],
        "target": job["target"],
        "error": job["error"],
    }
    if include_result:
        snapshot["result"] = job["result"]
    return snapshot


def _run_survey_job(job_id: str, payload: dict, base_url: str) -> None:
    _update_job(job_id, status="running", stage="Starting", progress=2, started_at=time.time())

    def report(stage: str, percent: int) -> None:
        _update_job(job_id, stage=stage, progress=max(2, min(99, int(percent))))

    set_progress_callback(report)
    try:
        result = _run_survey(payload, base_url)
    except Exception as exc:  # noqa: BLE001 - reported to the caller as a typed job error
        request_id = _request_id()
        logger.exception("Survey job %s failed (request_id=%s)", job_id, request_id)
        _update_job(
            job_id,
            status="failed",
            stage="Failed",
            progress=100,
            finished_at=time.time(),
            error={
                "code": "survey_failed",
                "message": "The survey engine failed while processing this request.",
                "request_id": request_id,
            },
        )
        del exc
    else:
        _update_job(
            job_id,
            status="succeeded",
            stage="Complete",
            progress=100,
            finished_at=time.time(),
            result=result,
        )
    finally:
        set_progress_callback(None)


def _enrich_single_category(data: dict, lat: float, lon: float, half_deg: float,
                            base_url: str, category: str, kmz: str, map_png: str) -> dict:
    urls, missing = _deliverables(base_url)
    data["target"] = _target_block(lat, lon, half_deg)
    data["kmz_download_url"] = urls.get(kmz)
    data["map_url"] = urls.get(map_png)
    data["download_urls"] = urls
    data["deliverables_missing"] = missing
    data["score_basis"] = "relative_to_aoi_percentile"
    data["claim_ceiling"] = CLAIM_CEILING[category]
    return data


def _targeted(req: TargetRequest, run) -> dict:
    """Run a single-category tool with the AOI configured inside the lock."""
    _check_coverage(req.latitude, req.longitude)
    request_id = _request_id()
    try:
        with _SITE_LOCK:
            cfg.set_target_site(req.latitude, req.longitude, half_deg=req.half_deg)
            return run()
    except Exception as exc:
        raise _internal_error(exc, request_id) from exc


# ---------------------------------------------------------------------------
# Interactive Web Sandbox (Digital Earth Africa Visual Explorer)
# ---------------------------------------------------------------------------
@app.get("/sandbox", response_class=HTMLResponse, tags=["Web Sandbox"])
@app.get("/", response_class=HTMLResponse, tags=["Web Sandbox"])
async def web_sandbox():
    """
    Interactive Leaflet.js Digital Earth Africa Geospatial Sandbox.
    Enables visual coordinate picking, real-time multi-criteria screening,
    and download of geospatial deliverables (HTML, KMZ, GeoJSON).
    """
    html_path = ROOT_DIR / "src" / "templates" / "sandbox.html"
    if html_path.exists():
        return HTMLResponse(
            content=html_path.read_text(encoding="utf-8"),
            headers={"Cache-Control": "no-cache"},
        )
    return HTMLResponse(content="<h1>SiteSurveyor AI Web Sandbox template not found</h1>", status_code=404)


@app.get("/robots.txt", response_class=PlainTextResponse, include_in_schema=False)
async def robots():
    return "User-agent: *\nAllow: /\n"


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    ico = ROOT_DIR / "src" / "static" / "SiteSurveyor.ico"
    if ico.exists():
        return FileResponse(ico)
    return Response(status_code=404)


@app.get("/favicon.svg", include_in_schema=False)
async def favicon_svg():
    svg = ROOT_DIR / "src" / "static" / "favicon.svg"
    if svg.exists():
        return FileResponse(svg, media_type="image/svg+xml")
    return Response(status_code=404)


@app.get("/logo.svg", include_in_schema=False)
async def logo_svg():
    svg = ROOT_DIR / "src" / "static" / "logo.svg"
    if svg.exists():
        return FileResponse(svg, media_type="image/svg+xml")
    return Response(status_code=404)


# ---------------------------------------------------------------------------
# Health & Status
# ---------------------------------------------------------------------------
@app.get("/health", tags=["Health"])
async def health_check():
    """Healthcheck endpoint for Render / load balancer monitoring."""
    hemisphere = "N" if cfg.TARGET_LAT >= 0 else "S"
    return {
        "status": "healthy",
        "service": "SiteSurveyor AI Geospatial Engine",
        "organization": "Eineva Labs",
        "version": "2.0.0",
        "active_aoi": cfg.AOI_SLUG,
        "crs": f"UTM Zone {cfg.UTM_ZONE}{hemisphere} (EPSG:{cfg.EPSG})",
        "state_dir_persistent": cfg.STATE_DIR != cfg.ROOT,
        "endpoints": {
            "mcp_sse": "/sse",
            "api_survey": "/api/survey",
            "api_job": "/api/jobs/{job_id}",
            "api_boreholes": "/api/boreholes",
            "api_minerals": "/api/minerals",
            "api_soil": "/api/soil",
            "api_hazard": "/api/hazard",
            "api_dossier": "/api/dossier",
            "api_report": "/api/report",
            "docs": "/docs",
        },
    }


# ---------------------------------------------------------------------------
# REST API Endpoints (Directly consumed by Supabase Edge Functions & Web UI)
# ---------------------------------------------------------------------------
@app.post("/api/survey", tags=["Geospatial Screening"], response_model=None)
def run_survey_endpoint(req: SurveyRequest, request: Request):
    """
    Execute comprehensive multi-criteria screening (Water, Minerals, Soil, Hazard)
    for any coordinate in Africa and return structured intelligence.

    Set ``async_mode: true`` to get a job id back immediately; poll
    ``/api/jobs/{id}`` for stage, progress and the finished result.
    """
    _check_coverage(req.latitude, req.longitude)

    payload = {
        "latitude": req.latitude,
        "longitude": req.longitude,
        "half_deg": req.half_deg,
        "categories": [c.lower().strip() for c in req.categories] or ["all"],
        "client_name": req.client_name.strip() or "Client",
        "address": (req.address or "").strip(),
    }
    base_url = str(request.base_url).rstrip("/")

    if req.async_mode:
        job = _create_job(payload)
        threading.Thread(
            target=_run_survey_job,
            args=(job["id"], payload, base_url),
            name=f"survey-{job['id'][:8]}",
            daemon=True,
        ).start()
        return JSONResponse(
            status_code=202,
            headers={"Cache-Control": "no-store"},
            content={
                "job_id": job["id"],
                "status": "queued",
                "poll_url": f"{base_url}/api/jobs/{job['id']}",
                "poll_after_ms": 2000,
                "estimated_minutes": 4,
            },
        )

    request_id = _request_id()
    try:
        result = _run_survey(payload, base_url)
        result["claim_ceiling"] = CLAIM_CEILING["survey"]
        return JSONResponse(content=result, headers={"Cache-Control": "no-store"})
    except Exception as exc:
        raise _internal_error(exc, request_id) from exc


@app.get("/api/jobs/{job_id}", tags=["Geospatial Screening"])
def get_job_endpoint(job_id: str):
    """Stage, progress and result of an asynchronous survey."""
    _prune_jobs()
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            job = _load_job_from_disk(job_id)
            if job:
                _JOBS[job_id] = job
        snapshot = _job_snapshot(job) if job else None
    if snapshot is None:
        raise _api_error(
            404,
            "job_not_found",
            "No survey job with that id.",
            "Jobs expire after six hours. Start a new survey if this one is gone.",
        )
    return JSONResponse(content=snapshot, headers={"Cache-Control": "no-store"})


@app.get("/api/jobs", tags=["Geospatial Screening"])
def list_jobs_endpoint():
    """Recent survey jobs, newest first (no result payloads)."""
    _prune_jobs()
    with _JOBS_LOCK:
        jobs = sorted(_JOBS.values(), key=lambda j: j["submitted_at"], reverse=True)
        snapshots = [_job_snapshot(job, include_result=False) for job in jobs[:20]]
    return JSONResponse(content={"jobs": snapshots}, headers={"Cache-Control": "no-store"})


@app.post("/api/boreholes", tags=["Geospatial Screening"])
def get_boreholes_endpoint(req: TargetRequest, request: Request):
    """
    Retrieve ranked borehole investigation coordinates, groundwater potential,
    and recommended geophysical confirmation steps (VES/ERT).
    """
    data = _targeted(req, lambda: _mcp_get_boreholes(
        latitude=req.latitude, longitude=req.longitude, top_k=req.top_k))
    return _enrich_single_category(
        data, req.latitude, req.longitude, req.half_deg,
        str(request.base_url).rstrip("/"), "water",
        kmz="boreholes_kmz", map_png="groundwater_map",
    )


@app.post("/api/minerals", tags=["Geospatial Screening"])
@app.post("/api/mineralexploration", tags=["Geospatial Screening"], include_in_schema=False)
@app.post("/api/mineral-exploration", tags=["Geospatial Screening"], include_in_schema=False)
def get_minerals_endpoint(req: TargetRequest, request: Request):
    """
    Screen shear-zone gold prospectivity, hydrothermal alteration (iron oxide, gossan, hydroxyl),
    and ranked exploration targets.
    """
    data = _targeted(req, lambda: _mcp_get_minerals(
        latitude=req.latitude, longitude=req.longitude, top_k=req.top_k))
    return _enrich_single_category(
        data, req.latitude, req.longitude, req.half_deg,
        str(request.base_url).rstrip("/"), "minerals",
        kmz="minerals_kmz", map_png="minerals_map",
    )


@app.post("/api/soil", tags=["Geospatial Screening"])
def get_soil_endpoint(req: TargetRequest, request: Request):
    """
    Assess agricultural land capability, soil moisture (NDMI), and erosion risk zoning.
    """
    data = _targeted(req, lambda: _mcp_get_soil_capability(
        latitude=req.latitude, longitude=req.longitude, top_k=req.top_k))
    return _enrich_single_category(
        data, req.latitude, req.longitude, req.half_deg,
        str(request.base_url).rstrip("/"), "soil",
        kmz="soil_kmz", map_png="soil_map",
    )


@app.post("/api/hazard", tags=["Geospatial Screening"])
def get_hazard_endpoint(req: TargetRequest, request: Request):
    """
    Multi-hazard exposure screening (flood ponding, slope failure, erosion, wildfire, drought)
    and safest buildable sites.
    """
    data = _targeted(req, lambda: _mcp_get_hazard_safety(
        latitude=req.latitude, longitude=req.longitude, top_k=req.top_k))
    return _enrich_single_category(
        data, req.latitude, req.longitude, req.half_deg,
        str(request.base_url).rstrip("/"), "hazard",
        kmz="safest_sites_kmz", map_png="hazard_map",
    )


@app.get("/api/dossier", tags=["Reports & Deliverables"])
def get_dossier_endpoint():
    """Retrieve the master cross-category site intelligence dossier JSON."""
    dossier_path = cfg.OUT / "master_site_dossier.json"
    if not dossier_path.exists():
        from src.report import generate_site_dossier
        # Regenerating reads whatever AOI src.config currently points at, so it
        # must not overlap a survey in flight.
        with _SITE_LOCK:
            dossier = generate_site_dossier()
        return JSONResponse(content=dossier, headers={"Cache-Control": "no-store"})
    with open(dossier_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return JSONResponse(content=data, headers={"Cache-Control": "no-store"})


@app.get("/api/report", tags=["Reports & Deliverables"])
def get_report_endpoint():
    """View the standalone HTML Executive Intelligence Dossier directly in the browser."""
    html_path = cfg.OUT / "SiteSurveyor_Intelligence_Report.html"
    if not html_path.exists():
        from src.report import generate_site_dossier
        with _SITE_LOCK:
            generate_site_dossier()
    if not html_path.exists():
        raise _api_error(
            404,
            "report_unavailable",
            "No executive report has been generated yet.",
            "Run a survey first; the report is written from its category outputs.",
        )
    return FileResponse(
        html_path,
        media_type="text/html",
        headers={"Cache-Control": "no-store"},
    )


# ---------------------------------------------------------------------------
# Static Deliverables Serving (/outputs/...) & Static Assets (/static/...)
# ---------------------------------------------------------------------------
cfg.OUT.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(cfg.OUT), html=True), name="outputs")

STATIC_DIR = ROOT_DIR / "src" / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# MCP SSE Mounting (Mounted at root so /sse and /messages/ are live for AI agents)
# ---------------------------------------------------------------------------
def _mcp_allowed_origins() -> set[str]:
    """Cross-origin browser callers of the MCP SSE transport.

    A page calling its own host is always accepted (see _OriginGuard), so this list only
    needs the extra origins an operator configures. Native agents (Claude Desktop, Cursor)
    send no Origin header and never reach this check.
    """
    return set(_origins)


class _OriginGuard:
    """Reject foreign browser origins before the MCP app sees them.

    The SDK applies `allowed_origins` only when DNS-rebinding protection is enabled, and
    that protection also requires whitelisting the deployment hostname -- which a reverse
    proxy makes a separate, riskier decision. Origin policy is enforced here instead, so
    the MCP surface is never wildcarded regardless of that flag.
    """

    def __init__(self, app, allowed: set[str]):
        self.app = app
        self.allowed = allowed

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = Headers(scope=scope)
            origin = headers.get("origin")
            if origin and origin not in self.allowed and not _is_same_origin(origin, headers.get("host")):
                logger.warning("MCP transport refused Origin %s", origin)
                await Response("Invalid Origin header", status_code=403)(scope, receive, send)
                return
        await self.app(scope, receive, send)


# DNS rebinding protection stays off until ALLOWED_HOSTS names the real hostnames --
# turning it on blind would reject Render's proxy hop.
_hosts = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip()]
_mcp_origins = _mcp_allowed_origins()
transport_sec = TransportSecuritySettings(
    enable_dns_rebinding_protection=bool(_hosts),
    allowed_hosts=_hosts or ["*"],
    allowed_origins=sorted(_mcp_origins),
)
logger.info("MCP SSE transport: same-origin always allowed, cross-origin %s; "
            "DNS rebinding protection %s",
            ", ".join(sorted(_mcp_origins)) or "none (set ALLOWED_ORIGINS to add)",
            "on for " + ", ".join(_hosts) if _hosts else "off (set ALLOWED_HOSTS to enable)")
sse_app = _OriginGuard(mcp.sse_app(transport_security=transport_sec), _mcp_origins)
app.mount("", sse_app)
