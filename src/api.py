"""
SiteSurveyor AI — Unified Cloud API & MCP Server (Render / Production)
======================================================================
Dual-protocol service for cloud deployment on Render:
1. REST API: For direct calls from web apps, Supabase Edge Functions (Deno),
   and dashboard frontends (JSON endpoints + static output artifact serving).
2. MCP Server (SSE): Model Context Protocol endpoint for autonomous AI agents
   (OpenClaw, Claude Desktop, Cursor, remote LLM orchestrators).

Usage:
    uvicorn src.api:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import json
import logging
import os
import sys
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
    survey_site as _mcp_survey_site,
)

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers
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
    client_name: str = Field(default="Client", description="Client or project name")
    address: str = Field(default="", description="Location or property address description")
    half_deg: float = Field(default=0.12, gt=0, le=0.5, description="AOI radius buffer in degrees (~13.3 km)")


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


def _deliverable_url(request: Request, filename: str) -> str:
    """Build fully qualified public URL for an output artifact."""
    base = str(request.base_url).rstrip("/")
    return f"{base}/outputs/{filename}"


def _http_error(exc: Exception) -> HTTPException:
    """Turn a failure into a 500 without losing it.

    The traceback stays in the server log; the response carries the exception type
    so an agent can tell a missing layer from a bad coordinate.
    """
    logger.exception("Request failed")
    return HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}")


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
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>SiteSurveyor AI Web Sandbox template not found</h1>", status_code=404)


# ---------------------------------------------------------------------------
# Health & Status
# ---------------------------------------------------------------------------
@app.get("/health", tags=["Health"])
async def health_check():
    """Healthcheck endpoint for Render / load balancer monitoring."""
    return {
        "status": "healthy",
        "service": "SiteSurveyor AI Geospatial Engine",
        "organization": "Eineva Labs",
        "version": "2.0.0",
        "active_aoi": cfg.AOI_SLUG,
        "crs": f"UTM Zone {cfg.UTM_ZONE} (EPSG:{cfg.EPSG})",
        "endpoints": {
            "mcp_sse": "/sse",
            "api_survey": "/api/survey",
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
@app.post("/api/survey", tags=["Geospatial Screening"])
def run_survey_endpoint(req: SurveyRequest, request: Request):
    """
    Execute comprehensive multi-criteria screening (Water, Minerals, Soil, Hazard)
    for any coordinate in Africa and return structured intelligence.
    """
    try:
        cfg.set_target_site(
            req.latitude,
            req.longitude,
            half_deg=req.half_deg,
            client=req.client_name,
            address=req.address or None,
        )
        res = _mcp_survey_site(
            latitude=req.latitude,
            longitude=req.longitude,
            categories=req.categories,
            client_name=req.client_name,
        )

        # Enrich deliverables with direct public download URLs
        res["download_urls"] = {
            "html_report": _deliverable_url(request, "SiteSurveyor_Intelligence_Report.html"),
            "master_json_dossier": _deliverable_url(request, "master_site_dossier.json"),
            "boreholes_kmz": _deliverable_url(request, "candidate_borehole_sites.kmz"),
            "minerals_kmz": _deliverable_url(request, "candidate_mineral_targets.kmz"),
            "soil_kmz": _deliverable_url(request, "candidate_land_zones.kmz"),
            "safest_sites_kmz": _deliverable_url(request, "safest_buildable_sites.kmz"),
            "groundwater_map": _deliverable_url(request, "groundwater_potential_map.png"),
            "minerals_map": _deliverable_url(request, "mineral_prospectivity_map.png"),
            "soil_map": _deliverable_url(request, "soil_capability_map.png"),
            "hazard_map": _deliverable_url(request, "hazard_risk_map.png"),
        }
        return res
    except Exception as exc:
        raise _http_error(exc)


@app.post("/api/boreholes", tags=["Geospatial Screening"])
def get_boreholes_endpoint(req: TargetRequest, request: Request):
    """
    Retrieve ranked precision borehole drilling coordinates, groundwater potential,
    and recommended geophysical confirmation steps (VES/ERT).
    """
    try:
        cfg.set_target_site(req.latitude, req.longitude, half_deg=req.half_deg)
        data = _mcp_get_boreholes(latitude=req.latitude, longitude=req.longitude, top_k=req.top_k)
        data["kmz_download_url"] = _deliverable_url(request, "candidate_borehole_sites.kmz")
        data["map_url"] = _deliverable_url(request, "groundwater_potential_map.png")
        return data
    except Exception as exc:
        raise _http_error(exc)


@app.post("/api/minerals", tags=["Geospatial Screening"])
def get_minerals_endpoint(req: TargetRequest, request: Request):
    """
    Screen shear-zone gold prospectivity, hydrothermal alteration (iron oxide, gossan, hydroxyl),
    and ranked exploration targets.
    """
    try:
        cfg.set_target_site(req.latitude, req.longitude, half_deg=req.half_deg)
        data = _mcp_get_minerals(latitude=req.latitude, longitude=req.longitude, top_k=req.top_k)
        data["kmz_download_url"] = _deliverable_url(request, "candidate_mineral_targets.kmz")
        data["map_url"] = _deliverable_url(request, "mineral_prospectivity_map.png")
        return data
    except Exception as exc:
        raise _http_error(exc)


@app.post("/api/soil", tags=["Geospatial Screening"])
def get_soil_endpoint(req: TargetRequest, request: Request):
    """
    Assess agricultural land capability, soil moisture (NDMI), and erosion risk zoning.
    """
    try:
        cfg.set_target_site(req.latitude, req.longitude, half_deg=req.half_deg)
        data = _mcp_get_soil_capability(latitude=req.latitude, longitude=req.longitude, top_k=req.top_k)
        data["kmz_download_url"] = _deliverable_url(request, "candidate_land_zones.kmz")
        data["map_url"] = _deliverable_url(request, "soil_capability_map.png")
        return data
    except Exception as exc:
        raise _http_error(exc)


@app.post("/api/hazard", tags=["Geospatial Screening"])
def get_hazard_endpoint(req: TargetRequest, request: Request):
    """
    Multi-hazard exposure screening (flood ponding, slope failure, erosion, wildfire, drought)
    and safest buildable sites.
    """
    try:
        cfg.set_target_site(req.latitude, req.longitude, half_deg=req.half_deg)
        data = _mcp_get_hazard_safety(latitude=req.latitude, longitude=req.longitude, top_k=req.top_k)
        data["kmz_download_url"] = _deliverable_url(request, "safest_buildable_sites.kmz")
        data["map_url"] = _deliverable_url(request, "hazard_risk_map.png")
        return data
    except Exception as exc:
        raise _http_error(exc)


@app.get("/api/dossier", tags=["Reports & Deliverables"])
def get_dossier_endpoint():
    """Retrieve the master cross-category site intelligence dossier JSON."""
    dossier_path = cfg.OUT / "master_site_dossier.json"
    if not dossier_path.exists():
        from src.report import generate_site_dossier
        # Regenerating reads whatever AOI src.config currently points at, so it
        # must not overlap a survey in flight.
        with _SITE_LOCK:
            return generate_site_dossier()
    with open(dossier_path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/report", tags=["Reports & Deliverables"])
def get_report_endpoint():
    """View the standalone HTML Executive Intelligence Dossier directly in the browser."""
    html_path = cfg.OUT / "SiteSurveyor_Intelligence_Report.html"
    if not html_path.exists():
        from src.report import generate_site_dossier
        with _SITE_LOCK:
            generate_site_dossier()
    return FileResponse(html_path, media_type="text/html")


# ---------------------------------------------------------------------------
# Static Deliverables Serving (/outputs/...)
# ---------------------------------------------------------------------------
cfg.OUT.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(cfg.OUT), html=True), name="outputs")


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

