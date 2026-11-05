"""
SiteSurveyor AI — Model Context Protocol (MCP) Server
=====================================================
Autonomous satellite-derived geospatial intelligence server for AI agents.
Enables agents (Claude, Gemini, Cursor, ChatGPT, etc.) to trigger multi-criteria
satellite screening for any GPS coordinate across:
  - Category 1: Groundwater potential & precision borehole siting
  - Category 2: Shear-zone gold prospectivity & hydrothermal alteration
  - Category 3: Soil & agricultural capability, erosion risk
  - Category 5: Multi-hazard & site safety screening

Usage:
  python -m src.mcp.server                        # stdio transport (local agents)
  python -m src.mcp.server --transport sse --port 8000  # SSE transport (cloud / remote)
"""
from __future__ import annotations

import argparse
import functools
import json
import os
import sys
import threading
from pathlib import Path

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Always import config first to configure PROJ paths before rasterio loads
import src.config as cfg

from mcp.server.mcpserver import MCPServer

# Initialize MCP Server
mcp = MCPServer(
    name="SiteSurveyorAI",
    title="SiteSurveyor AI — Satellite Geospatial Intelligence Engine",
    description=(
        "Autonomous multi-sensor satellite Earth observation intelligence engine. "
        "Provides probabilistic groundwater potential, mineral prospectivity, soil capability, "
        "and natural hazard safety screening from orbital data (Sentinel-2, DEM 30m, ALOS PALSAR, Landsat WOfS)."
    ),
    version="2.0.0",
)


def _ensure_data_present():
    """Verify that required satellite layers exist; fetch from DE Africa if missing."""
    required = ["dem.tif", "landcover.tif", "alos.tif", "geomad.tif", "wofs.tif", "rain_mean.tif"]
    missing = [f for f in required if not (cfg.RAW / f).exists()]
    if missing:
        from src.fetch_data import fetch_all
        fetch_all()


def _cached_summary(path: Path, latitude: float, longitude: float) -> dict | None:
    """Return a stored survey only when it covers this point, saying why it was skipped.

    Silently swallowing a corrupt summary made the agent pay for a full re-survey with no
    clue that one was available, and treated "unreadable" exactly like "never run".
    """
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            cached = json.load(f)
    except Exception as e:
        print(f"[cache] {path.name} unreadable -- re-running survey: {type(e).__name__}: {e}")
        return None
    if not isinstance(cached, dict):
        print(f"[cache] {path.name} is a {type(cached).__name__}, not an object -- re-running survey")
        return None

    # soil_summary.json uses flat target_lat/target_lon; the others nest coordinates.
    tc = cached.get("target_coordinates") or {
        "latitude": cached.get("target_lat"),
        "longitude": cached.get("target_lon"),
    }
    lat, lon = tc.get("latitude"), tc.get("longitude")
    if lat is None or lon is None:
        print(f"[cache] {path.name} records no target coordinates -- re-running survey")
        return None
    if abs(float(lat) - latitude) > 0.001 or abs(float(lon) - longitude) > 0.001:
        print(f"[cache] {path.name} is for ({lat:.5f}, {lon:.5f}), not ({latitude:.5f}, {longitude:.5f})")
        return None
    return cached


# ============================================================================
# MCP Tools
# ============================================================================

_SITE_LOCK = threading.Lock()


def _single_site(fn):
    """Let one site be under analysis per process.

    The engines read bbox, grid size, cell pitch and target pixel from module-global
    src.config, which every tool mutates via set_target_site. REST handlers now run in a
    threadpool so /health keeps answering, which means two surveys genuinely overlap
    unless something serializes them -- each would analyze the other's AOI and publish
    plausible numbers for the wrong place. Drop this when an immutable per-job
    SiteContext replaces those globals.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with _SITE_LOCK:
            return fn(*args, **kwargs)
    return wrapper

@mcp.tool()
@_single_site
def survey_site(
    latitude: float,
    longitude: float,
    categories: list[str] = ["all"],
    client_name: str = "Client",
) -> dict:
    """
    Execute a comprehensive satellite screening survey across requested categories.

    Args:
        latitude: Target property GPS latitude in decimal degrees (e.g. -19.50487)
        longitude: Target property GPS longitude in decimal degrees (e.g. 29.84598)
        categories: List of categories to analyze: 'water', 'minerals', 'soil', 'hazard', or 'all'.
        client_name: Name of client or project for report attribution.

    Returns:
        Structured intelligence dictionary with multi-criteria scores, primary GPS recommendations,
        and paths to maps, KMZ vectors, and the executive HTML dossier.
    """
    cfg.set_target_site(latitude, longitude, client=client_name)
    _ensure_data_present()

    cats = [c.lower().strip() for c in categories]
    run_all = "all" in cats

    results = {}
    if run_all or "water" in cats:
        from src.engines.water import run_water_survey
        results["water"] = run_water_survey()
    if run_all or "minerals" in cats:
        from src.engines.minerals import run_minerals_survey
        results["minerals"] = run_minerals_survey()
    if run_all or "soil" in cats:
        from src.engines.soil import run_soil_survey
        results["soil"] = run_soil_survey()
    if run_all or "hazard" in cats:
        from src.engines.hazard import run_hazard_survey
        results["hazard"] = run_hazard_survey()

    # Generate or refresh Master Executive Dossier
    from src.report import generate_site_dossier
    dossier = generate_site_dossier()
    scorecard = dossier.get("executive_scorecard", {})

    gw = scorecard.get("groundwater", {})
    minerals = scorecard.get("minerals", {})
    soil = scorecard.get("soil_land", {})
    haz = scorecard.get("hazard_safety", {})

    return {
        "status": "success",
        "executive_summary": (
            f"Survey completed for ({latitude:.5f}, {longitude:.5f}). "
            f"Groundwater potential is {gw.get('cell_score', 'N/A')}/100 ({gw.get('cell_class', 'N/A')}) "
            f"with top borehole site {gw.get('primary_borehole_candidate', {}).get('distance_km', 'N/A')} km away. "
            f"Mineral prospectivity is {minerals.get('cell_score', 'N/A')}/100 ({minerals.get('cell_class', 'N/A')}). "
            f"Soil capability is {soil.get('cell_score', 'N/A')}/100 ({soil.get('cell_class', 'N/A')}). "
            f"Site safety score is {haz.get('safety_score', 'N/A')}/100 with hazard index {haz.get('hazard_score', 'N/A')}/100."
        ),
        "scores": {
            "groundwater": {
                "cell_score": gw.get("cell_score"),
                "cell_class": gw.get("cell_class"),
                "parcel_150m_mean": gw.get("parcel_150m_score"),
            },
            "minerals": {
                "cell_score": minerals.get("cell_score"),
                "cell_class": minerals.get("cell_class"),
                "parcel_150m_mean": minerals.get("parcel_150m_score"),
            },
            "soil_land": {
                "cell_score": soil.get("cell_score"),
                "cell_class": soil.get("cell_class"),
                "parcel_150m_mean": soil.get("parcel_150m_score"),
            },
            "hazard_safety": {
                "safety_score": haz.get("safety_score"),
                "hazard_score": haz.get("hazard_score"),
                "hazard_class": haz.get("hazard_class"),
            },
        },
        "primary_recommendations": {
            "top_borehole_drilling_site": gw.get("primary_borehole_candidate"),
            "top_mineral_exploration_target": minerals.get("primary_mineral_target"),
            "top_agricultural_zone": soil.get("primary_agricultural_zone"),
            "safest_building_site": haz.get("primary_safe_build_site"),
        },
        "deliverables": {
            "executive_html_dossier": str(cfg.OUT / "SiteSurveyor_Intelligence_Report.html"),
            "master_json_dossier": str(cfg.OUT / "master_site_dossier.json"),
            "maps": {
                "groundwater_map": str(cfg.OUT / "groundwater_potential_map.png"),
                "mineral_prospectivity_map": str(cfg.OUT / "mineral_prospectivity_map.png"),
                "soil_capability_map": str(cfg.OUT / "soil_capability_map.png"),
                "hazard_risk_map": str(cfg.OUT / "hazard_risk_map.png"),
            },
            "mobile_gps_kmz": {
                "boreholes": str(cfg.OUT / "candidate_borehole_sites.kmz"),
                "minerals": str(cfg.OUT / "candidate_mineral_targets.kmz"),
                "soil_zones": str(cfg.OUT / "candidate_land_zones.kmz"),
                "safe_sites": str(cfg.OUT / "safest_buildable_sites.kmz"),
            },
        },
    }


@mcp.tool()
@_single_site
def get_boreholes(latitude: float, longitude: float, top_k: int = 5) -> dict:
    """
    Retrieve ranked precision borehole drilling coordinates for a given location.

    Args:
        latitude: Target property GPS latitude in decimal degrees.
        longitude: Target property GPS longitude in decimal degrees.
        top_k: Number of ranked candidate borehole sites to return (default: 5).

    Returns:
        Dictionary containing target property potential, ranked candidate sites with GPS coordinates,
        proximity distance, score, and recommended geophysical verification steps (VES/ERT).
    """
    cfg.set_target_site(latitude, longitude)
    data = _cached_summary(cfg.OUT / "summary.json", latitude, longitude)
    if data is None:
        _ensure_data_present()
        from src.engines.water import run_water_survey
        data = run_water_survey(latitude, longitude)

    candidates = data.get("candidate_sites", [])[:top_k]
    target_info = data.get("target_assessment", {})

    return {
        "target_coordinates": {"latitude": latitude, "longitude": longitude},
        "target_groundwater_potential": {
            "cell_score": target_info.get("coordinate_cell_score"),
            "cell_class": target_info.get("coordinate_cell_class"),
            "parcel_150m_mean": target_info.get("parcel_mean_150m"),
            "twi": target_info.get("twi"),
            "slope_degrees": target_info.get("slope_degrees"),
        },
        "ranked_candidates": candidates,
        "advisory": (
            "Screening-level satellite analysis. Recommended next step: Perform Vertical Electrical Sounding (VES) "
            "resistivity sounding at Candidate #1 to confirm depth to aquifer and fracture permeability."
        ),
        "kmz_mobile_gps_file": str(cfg.OUT / "candidate_borehole_sites.kmz"),
    }


@mcp.tool()
@_single_site
def get_minerals(latitude: float, longitude: float, top_k: int = 5) -> dict:
    """
    Screen shear-zone gold prospectivity and hydrothermal alteration around a site.

    Args:
        latitude: Target GPS latitude.
        longitude: Target GPS longitude.
        top_k: Number of exploration targets to return (default: 5).

    Returns:
        Dictionary with mineral prospectivity scores, lineament structural context,
        alteration indicators (iron oxide, gossan, hydroxyl clay), and ranked targets.
    """
    cfg.set_target_site(latitude, longitude)
    data = _cached_summary(cfg.OUT / "mineral_summary.json", latitude, longitude)
    if data is None:
        _ensure_data_present()
        from src.engines.minerals import run_minerals_survey
        data = run_minerals_survey(latitude, longitude)

    targets = data.get("candidate_targets", [])[:top_k]
    target_info = data.get("target_assessment", {})

    return {
        "target_coordinates": {"latitude": latitude, "longitude": longitude},
        "target_prospectivity": {
            "cell_score": target_info.get("coordinate_cell_score"),
            "cell_class": target_info.get("coordinate_cell_class"),
            "parcel_150m_mean": target_info.get("parcel_mean_150m"),
        },
        "ranked_targets": targets,
        "kmz_mobile_gps_file": str(cfg.OUT / "candidate_mineral_targets.kmz"),
    }


@mcp.tool()
@_single_site
def get_soil_capability(latitude: float, longitude: float, top_k: int = 5) -> dict:
    """
    Assess agricultural land capability, soil moisture, and erosion risk.

    Args:
        latitude: Target GPS latitude.
        longitude: Target GPS longitude.
        top_k: Number of prime land zones to return (default: 5).

    Returns:
        Dictionary with Soil Capability Index (SCI), erosion risk, and prime arable land zones.
    """
    cfg.set_target_site(latitude, longitude)
    data = _cached_summary(cfg.OUT / "soil_summary.json", latitude, longitude)
    if data is None:
        _ensure_data_present()
        from src.engines.soil import run_soil_survey
        data = run_soil_survey(latitude, longitude)

    candidates = data.get("candidate_areas", [])[:top_k]

    return {
        "target_coordinates": {"latitude": latitude, "longitude": longitude},
        "target_soil_capability": {
            "cell_score": data.get("target_sci_score"),
            "cell_class": data.get("target_sci_class"),
            "parcel_150m_mean": data.get("local_150m_mean_score"),
            "parcel_class": data.get("local_150m_class"),
        },
        "prime_land_zones": candidates,
        "kmz_mobile_gps_file": str(cfg.OUT / "candidate_land_zones.kmz"),
    }


@mcp.tool()
@_single_site
def get_hazard_safety(latitude: float, longitude: float, top_k: int = 5) -> dict:
    """
    Assess multi-hazard exposure (flood, slope failure, erosion, wildfire, drought) and safest buildable sites.

    Args:
        latitude: Target GPS latitude.
        longitude: Target GPS longitude.
        top_k: Number of safest buildable sites to return (default: 5).

    Returns:
        Dictionary with Site Safety Index (0-100, 100=Safest), detailed hazard breakdown,
        and ranked low-risk buildable locations.
    """
    cfg.set_target_site(latitude, longitude)
    data = _cached_summary(cfg.OUT / "hazard_summary.json", latitude, longitude)
    if data is None:
        _ensure_data_present()
        from src.engines.hazard import run_hazard_survey
        data = run_hazard_survey(latitude, longitude)

    t_assess = data.get("target_assessment", {})
    safest = data.get("safest_candidate_sites", [])[:top_k]

    return {
        "target_coordinates": {"latitude": latitude, "longitude": longitude},
        "safety_assessment": {
            "site_safety_score": t_assess.get("safety_index_score"),
            "hazard_index_score": t_assess.get("hazard_index_score"),
            "hazard_classification": t_assess.get("hazard_classification"),
            "parcel_150m_hazard": t_assess.get("local_150m_mean_hazard"),
            "sub_hazard_breakdown": t_assess.get("sub_hazard_breakdown", {}),
        },
        "safest_candidate_sites": safest,
        "kmz_mobile_gps_file": str(cfg.OUT / "safest_buildable_sites.kmz"),
    }


@mcp.tool()
@_single_site
def get_executive_dossier() -> dict:
    """
    Retrieve the master cross-category site intelligence dossier.

    Returns:
        Consolidated scorecard across all categories, metadata, and the absolute path
        to the self-contained HTML executive report.
    """
    dossier_path = cfg.OUT / "master_site_dossier.json"
    if not dossier_path.exists():
        from src.report import generate_site_dossier
        dossier = generate_site_dossier()
    else:
        with open(dossier_path, "r", encoding="utf-8") as f:
            dossier = json.load(f)

    html_path = cfg.OUT / "SiteSurveyor_Intelligence_Report.html"

    return {
        "title": dossier.get("title"),
        "client": dossier.get("client"),
        "address": dossier.get("address"),
        "generated_at": dossier.get("generated_at"),
        "executive_scorecard": dossier.get("executive_scorecard"),
        "html_report_path": str(html_path) if html_path.exists() else None,
        "html_report_size_bytes": html_path.stat().st_size if html_path.exists() else 0,
    }


# ============================================================================
# MCP Resources
# ============================================================================

@mcp.resource("sitesurveyor://reports/master_dossier.json")
def get_master_dossier_resource() -> str:
    """Read the latest Master Site Intelligence JSON dossier."""
    path = cfg.OUT / "master_site_dossier.json"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return json.dumps({"error": "Master dossier not yet generated. Run survey_site first."})


@mcp.resource("sitesurveyor://reports/SiteSurveyor_Intelligence_Report.html")
def get_html_report_resource() -> str:
    """Read the standalone HTML Executive Intelligence Dossier."""
    path = cfg.OUT / "SiteSurveyor_Intelligence_Report.html"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "<html><body><h1>Report not yet generated. Please execute survey_site.</h1></body></html>"


# ============================================================================
# Server Runner
# ============================================================================

def run_server():
    """Parse CLI arguments and run MCP Server over stdio or sse transport."""
    parser = argparse.ArgumentParser(description="SiteSurveyor AI — Model Context Protocol (MCP) Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="MCP Transport protocol to use (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind when running SSE transport (default: 8000)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host address to bind when running SSE transport (default: 0.0.0.0)",
    )

    args = parser.parse_args()

    if args.transport == "stdio":
        # Run stdio transport
        mcp.run(transport="stdio")
    elif args.transport == "sse":
        # Run SSE transport
        mcp.run(transport="sse", host=args.host, port=args.port)
    elif args.transport == "streamable-http":
        mcp.run(transport="streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":
    run_server()

