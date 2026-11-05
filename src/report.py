"""
SiteSurveyor AI — Master Site Intelligence Dossier Generator
============================================================
Synthesizes satellite survey results across all operational categories
(Groundwater, Minerals, Soil Capability, Hazard & Risk) into an
executive-level client intelligence dossier (JSON + self-contained HTML).
"""
from __future__ import annotations

import base64
import json
import os
import sys
from datetime import datetime
from html import escape as _escape
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src.config as cfg


def _load_category(path: Path) -> tuple[dict | None, str]:
    """Load a category summary and say *why* it is absent.

    A corrupt or unreadable file must not report as "analysis not run": the two
    need different remedies, and downstream readers only see the JSON.
    """
    if not path.exists():
        return None, "not_run"
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return None, f"unreadable ({type(e).__name__}: {e})"
    if not isinstance(data, dict):
        return None, f"unexpected structure ({type(data).__name__})"
    return data, "loaded"


def _img_to_base64_src(path: Path) -> tuple[str | None, str]:
    """Embed a map as base64, or explain why the panel will be blank."""
    if not path.exists():
        return None, "map file not produced"
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except Exception as e:
        return None, f"map file unreadable ({type(e).__name__}: {e})"
    if not encoded:
        return None, "map file is empty"
    return f"data:image/png;base64,{encoded}", "embedded"


def generate_site_dossier(
    target_lat: float | None = None,
    target_lon: float | None = None,
    half_deg: float = 0.12,
    client: str | None = None,
    address: str | None = None,
) -> dict:
    """Consolidate all category survey outputs into a master site dossier."""
    if target_lat is not None and target_lon is not None:
        cfg.set_target_site(target_lat, target_lon, half_deg=half_deg, client=client, address=address)

    print("=" * 65)
    print(f"SiteSurveyor AI -- Generating Executive Multi-Category Site Dossier [{cfg.AOI_SLUG}]")
    print(f"Target: ({cfg.TARGET_LAT:.5f}, {cfg.TARGET_LON:.5f}) | Client: {cfg.CLIENT}")
    print("=" * 65)

    water_data, water_status = _load_category(cfg.OUT / "summary.json")
    minerals_data, minerals_status = _load_category(cfg.OUT / "mineral_summary.json")
    soil_data, soil_status = _load_category(cfg.OUT / "soil_summary.json")
    hazard_data, hazard_status = _load_category(cfg.OUT / "hazard_summary.json")

    # 1. Build Master JSON Dossier
    dossier = {
        "title": "SiteSurveyor AI Executive Site Intelligence Dossier",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "client": cfg.CLIENT,
        "address": cfg.CLIENT_ADDRESS,
        "analyst_organization": cfg.ANALYST,
        "target_coordinates": {
            "latitude": cfg.TARGET_LAT,
            "longitude": cfg.TARGET_LON,
        },
        "category_status": {
            "groundwater": water_status,
            "minerals": minerals_status,
            "soil_land": soil_status,
            "hazard_safety": hazard_status,
        },
        "executive_scorecard": {},
        "categories": {},
    }

    # Water extraction
    if water_data:
        t_assess = water_data.get("target_assessment", {})
        candidates = water_data.get("candidate_sites", [])
        top_cand = candidates[0] if candidates else None
        dossier["executive_scorecard"]["groundwater"] = {
            "cell_score": t_assess.get("coordinate_cell_score"),
            "cell_class": t_assess.get("coordinate_cell_class"),
            "parcel_150m_score": t_assess.get("parcel_mean_150m"),
            "parcel_150m_class": t_assess.get("parcel_class_150m"),
            "primary_borehole_candidate": {
                "latitude": top_cand.get("latitude") if top_cand else None,
                "longitude": top_cand.get("longitude") if top_cand else None,
                "distance_km": top_cand.get("distance_from_target_km") if top_cand else None,
                "potential_score": top_cand.get("potential_score") if top_cand else None,
            } if top_cand else None,
        }
        dossier["categories"]["water"] = water_data

    # Minerals extraction
    if minerals_data:
        t_assess = minerals_data.get("target_assessment", {})
        candidates = minerals_data.get("candidate_targets", [])
        top_cand = candidates[0] if candidates else None
        dossier["executive_scorecard"]["minerals"] = {
            "cell_score": t_assess.get("coordinate_cell_score"),
            "cell_class": t_assess.get("coordinate_cell_class"),
            "parcel_150m_score": t_assess.get("parcel_mean_150m"),
            "parcel_150m_class": t_assess.get("parcel_class_150m"),
            "primary_mineral_target": {
                "latitude": top_cand.get("latitude") if top_cand else None,
                "longitude": top_cand.get("longitude") if top_cand else None,
                "distance_km": top_cand.get("distance_from_target_km") if top_cand else None,
                "prospectivity_score": top_cand.get("potential_score") or top_cand.get("prospectivity_score") if top_cand else None,
            } if top_cand else None,
        }
        dossier["categories"]["minerals"] = minerals_data

    # Soil extraction
    if soil_data:
        candidates = soil_data.get("candidate_areas", [])
        top_cand = candidates[0] if candidates else None
        dossier["executive_scorecard"]["soil_land"] = {
            "cell_score": soil_data.get("target_sci_score"),
            "cell_class": soil_data.get("target_sci_class"),
            "parcel_150m_score": soil_data.get("local_150m_mean_score"),
            "parcel_150m_class": soil_data.get("local_150m_class"),
            "primary_agricultural_zone": {
                "latitude": top_cand.get("latitude") if top_cand else None,
                "longitude": top_cand.get("longitude") if top_cand else None,
                "distance_km": top_cand.get("distance_from_target_km") if top_cand else None,
                "capability_score": top_cand.get("potential_score") if top_cand else None,
            } if top_cand else None,
        }
        dossier["categories"]["soil_land"] = soil_data

    # Hazard extraction
    if hazard_data:
        t_assess = hazard_data.get("target_assessment", {})
        safest = hazard_data.get("safest_candidate_sites", [])
        top_safe = safest[0] if safest else None
        dossier["executive_scorecard"]["hazard_safety"] = {
            "hazard_score": t_assess.get("hazard_index_score"),
            "hazard_class": t_assess.get("hazard_classification"),
            "safety_score": t_assess.get("safety_index_score"),
            "parcel_150m_hazard": t_assess.get("local_150m_mean_hazard"),
            "sub_hazards": t_assess.get("sub_hazard_breakdown", {}),
            "primary_safe_build_site": {
                "latitude": top_safe.get("latitude") if top_safe else None,
                "longitude": top_safe.get("longitude") if top_safe else None,
                "distance_km": top_safe.get("distance_from_target_km") if top_safe else None,
                "safety_score": top_safe.get("potential_score") if top_safe else None,
            } if top_safe else None,
        }
        dossier["categories"]["hazard_safety"] = hazard_data

    # Save Master JSON
    json_path = cfg.OUT / "master_site_dossier.json"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(dossier, fh, indent=2)
    print("  [OK] master_site_dossier.json")

    # 2. Build HTML Executive Report
    html_content = _build_html_report(dossier)
    html_path = cfg.OUT / "SiteSurveyor_Intelligence_Report.html"
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(html_content)
    print("  [OK] SiteSurveyor_Intelligence_Report.html")

    print("\n[OK] Master Site Dossier successfully generated!")
    return dossier


def _build_html_report(dossier: dict) -> str:
    """Build a standalone, beautifully styled HTML intelligence dossier."""
    def cand(section: dict, key: str) -> dict:
        """The dossier stores null when a survey found no candidate; rendering must
        survive that rather than crashing on None.get for a data-poor scene."""
        return section.get(key) or {}

    sc = dossier.get("executive_scorecard", {})
    gw = sc.get("groundwater", {})
    minerals = sc.get("minerals", {})
    soil = sc.get("soil_land", {})
    haz = sc.get("hazard_safety", {})

    # Client, address and coordinates are caller-supplied and this document is served
    # same-origin, so they are escaped before interpolation. Unescaped, a client name
    # containing a script tag executed for the next visitor of /api/report.
    client_name = _escape(cfg.CLIENT or "Client")
    client_address = _escape(cfg.CLIENT_ADDRESS or "")
    latitude_label = f"{abs(cfg.TARGET_LAT):.5f}&deg; {'N' if cfg.TARGET_LAT >= 0 else 'S'}"
    longitude_label = f"{abs(cfg.TARGET_LON):.5f}&deg; {'E' if cfg.TARGET_LON >= 0 else 'W'}"
    zone_label = f"{cfg.UTM_ZONE}{'N' if cfg.TARGET_LAT >= 0 else 'S'}"

    statuses = dossier.get("category_status", {}) or {}
    unfinished = [name.replace("_", " ") for name, status in statuses.items() if status != "loaded"]
    if not statuses:
        status_banner = (
            '<div class="status-banner"><strong>No survey has been run yet.</strong> '
            'Every score below reads N/A because no category output exists for this AOI.</div>'
        )
    elif unfinished:
        status_banner = (
            '<div class="status-banner"><strong>Incomplete dossier.</strong> '
            f'No usable output for: {_escape(", ".join(unfinished))}. '
            'Those scores read N/A and their maps are omitted rather than drawn from missing data.</div>'
        )
    else:
        status_banner = ""

    # Convert map images to base64 for complete offline portability.
    # A panel that cannot be embedded is stated as unavailable with its reason --
    # a silently missing map reads as "no map was made" to the client.
    map_specs = [
        ("Category 1: Groundwater Potential Zones (GWPZ)", "groundwater_potential_map.png", "Groundwater Map"),
        ("Groundwater Local Siting Zoom (5x5 km)", "site_zoom_map.png", "Groundwater Zoom"),
        ("Category 2: Mineral Prospectivity & Shear Zones", "mineral_prospectivity_map.png", "Minerals Map"),
        ("Category 3: Soil & Land Capability Zoning", "soil_capability_map.png", "Soil Map"),
        ("Category 5: Natural Hazard & Risk Zoning", "hazard_risk_map.png", "Hazard Map"),
        ("Site Safety & Hazard Zoom (5x5 km)", "site_hazard_zoom.png", "Hazard Zoom"),
    ]
    map_panels = []
    for map_title, map_file, map_alt in map_specs:
        img_src, img_note = _img_to_base64_src(cfg.OUT / map_file)
        if img_src:
            map_panels.append(
                f'<div class="map-box"><h4>{map_title}</h4><img src="{img_src}" alt="{map_alt}"/></div>')
        else:
            map_panels.append(
                f'<div class="map-box"><h4>{map_title}</h4>'
                f'<p style="color:#a33; font-size:0.9em;">Map not embedded: {img_note}.</p></div>')
    maps_html = "\n      ".join(map_panels)

    def score_color(val):
        if val is None:
            return "#64748b"
        if val >= 75:
            return "#10b981"
        elif val >= 55:
            return "#f59e0b"
        elif val >= 40:
            return "#f97316"
        else:
            return "#ef4444"

    def hazard_color(val):
        if val is None:
            return "#64748b"
        if val <= 30:
            return "#10b981"
        elif val <= 50:
            return "#f59e0b"
        else:
            return "#ef4444"

    logo_svg_path = Path(__file__).resolve().parent / "static" / "logo.svg"
    logo_data_uri = "/logo.svg"
    if logo_svg_path.exists():
        try:
            b64_logo = base64.b64encode(logo_svg_path.read_bytes()).decode("ascii")
            logo_data_uri = f"data:image/svg+xml;base64,{b64_logo}"
        except Exception:
            logo_data_uri = "/logo.svg"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>SiteSurveyor AI — Executive Site Intelligence Dossier</title>
  <link rel="icon" type="image/svg+xml" href="/favicon.svg">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:ital,wght@0,400;0,500;0,600;1,400&family=Inter:wght@300;400;500;600;700;800&family=Manrope:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {{
      --brand: {cfg.BRAND_COLOR};
      --brand-hover: #BB2B2C;
      --brand-muted: rgba(209, 65, 65, 0.12);
      --brand-border: rgba(209, 65, 65, 0.32);
      --font-sans: 'Inter', 'Manrope', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      --font-mono: 'IBM Plex Mono', 'JetBrains Mono', ui-monospace, monospace;
      --water: #38bdf8;
      --mineral: #f59e0b;
      --soil: #10b981;
      --hazard: #f43f5e;
      --bg: #f8fafc;
      --surface: #ffffff;
      --line: #e2e8f0;
      --line-strong: #cbd5e1;
      --text: #0f172a;
      --text-muted: #64748b;
      --dim: #94a3b8;
    }}

    * {{ box-sizing: border-box; }}

    body {{
      font-family: var(--font-sans);
      margin: 0;
      padding: 0;
      background-color: var(--bg);
      color: var(--text);
      line-height: 1.6;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }}

    .mono {{
      font-family: var(--font-mono);
    }}

    /* Header */
    .header {{
      background: #090d16;
      border-top: 4px solid var(--brand);
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      color: #ffffff;
      padding: 36px 48px;
    }}
    .header-inner {{
      max-width: 1200px;
      margin: 0 auto;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 24px;
    }}
    .header-brand {{
      display: flex;
      align-items: center;
      gap: 16px;
    }}
    .brand-mark {{
      width: 48px;
      height: 48px;
      border-radius: 8px;
      background: #111625;
      border: 1px solid rgba(255, 255, 255, 0.14);
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 8px;
      flex: 0 0 auto;
    }}
    .brand-logo {{
      width: 100%;
      height: 100%;
      object-fit: contain;
    }}
    .header h1 {{
      margin: 0 0 6px 0;
      font-size: 26px;
      font-weight: 700;
      letter-spacing: -0.5px;
      color: #ffffff;
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
    }}
    .header-badge {{
      font-family: var(--font-mono);
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.8px;
      color: var(--brand);
      background: var(--brand-muted);
      border: 1px solid var(--brand-border);
      padding: 3px 8px;
      border-radius: 4px;
      text-transform: uppercase;
    }}
    .header .subtitle {{
      font-size: 12px;
      color: #94a3b8;
      letter-spacing: 0.8px;
      text-transform: uppercase;
      font-weight: 500;
    }}
    .header-client {{
      background: #111625;
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 8px;
      padding: 12px 18px;
      font-size: 12.5px;
      color: #cbd5e1;
    }}
    .header-client strong {{
      color: #ffffff;
    }}

    /* Meta bar */
    .meta-bar {{
      background: #ffffff;
      border-bottom: 1px solid var(--line);
      padding: 14px 48px;
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: 28px;
      font-size: 12.5px;
      color: var(--text-muted);
    }}
    .meta-item strong {{
      color: var(--text);
      font-weight: 600;
      margin-right: 4px;
    }}
    .meta-item span {{
      font-family: var(--font-mono);
      color: var(--brand);
    }}

    /* Main Container */
    .container {{
      max-width: 1200px;
      margin: 32px auto;
      padding: 0 24px;
    }}

    .section-title {{
      font-size: 18px;
      font-weight: 700;
      letter-spacing: -0.3px;
      color: var(--text);
      margin: 36px 0 16px 0;
      padding-bottom: 8px;
      border-bottom: 2px solid var(--brand);
      display: flex;
      align-items: center;
      gap: 8px;
    }}

    /* Scorecards */
    .scorecard-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 18px;
      margin-bottom: 35px;
    }}
    .card {{
      background: var(--surface);
      border-radius: 10px;
      padding: 22px;
      border: 1px solid var(--line);
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
      border-top: 4px solid var(--brand);
      transition: transform 0.15s, box-shadow 0.15s;
    }}
    .card--water {{ border-top-color: var(--water); }}
    .card--mineral {{ border-top-color: var(--mineral); }}
    .card--soil {{ border-top-color: var(--soil); }}
    .card--hazard {{ border-top-color: var(--hazard); }}

    .card h3 {{
      margin: 0 0 12px 0;
      font-size: 12.5px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.6px;
      color: var(--text-muted);
    }}
    .big-score {{
      font-family: var(--font-mono);
      font-size: 38px;
      font-weight: 700;
      line-height: 1;
      margin-bottom: 8px;
    }}
    .score-badge {{
      display: inline-block;
      padding: 3px 10px;
      border-radius: 999px;
      font-size: 11.5px;
      font-weight: 600;
      color: #ffffff;
      margin-bottom: 12px;
    }}
    .detail-line {{
      font-size: 12px;
      color: var(--text-muted);
      border-top: 1px solid var(--line);
      padding-top: 8px;
      margin-top: 8px;
    }}
    .detail-line strong {{
      color: var(--text);
    }}

    /* Actionable Table */
    .target-table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--surface);
      border-radius: 10px;
      overflow: hidden;
      border: 1px solid var(--line);
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
      margin-bottom: 35px;
      font-size: 12.5px;
    }}
    .target-table th {{
      background: #f1f5f9;
      color: #334155;
      text-align: left;
      padding: 12px 14px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.6px;
      text-transform: uppercase;
      border-bottom: 1px solid var(--line);
    }}
    .target-table td {{
      padding: 12px 14px;
      border-top: 1px solid var(--line);
      color: var(--text);
    }}
    .target-table tr:hover {{
      background: #f8fafc;
    }}

    /* Maps Grid */
    .maps-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(480px, 1fr));
      gap: 22px;
      margin-bottom: 35px;
    }}
    .map-box {{
      background: var(--surface);
      border-radius: 10px;
      padding: 16px;
      border: 1px solid var(--line);
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
    }}
    .map-box h4 {{
      margin: 0 0 10px 0;
      font-size: 13.5px;
      font-weight: 700;
      color: var(--text);
    }}
    .map-box img {{
      width: 100%;
      height: auto;
      border-radius: 6px;
      border: 1px solid var(--line);
      display: block;
    }}

    /* Banners & Notes */
    .status-banner {{
      background: #fffbeb;
      border-left: 4px solid var(--mineral);
      border: 1px solid #fde68a;
      border-left-width: 4px;
      border-radius: 6px;
      padding: 14px 18px;
      font-size: 12.5px;
      color: #92400e;
      margin-bottom: 25px;
    }}
    .note {{
      font-size: 12px;
      color: var(--text-muted);
      background: #f1f5f9;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px 14px;
      margin: -4px 0 18px 0;
    }}
    .attribution {{
      font-size: 11.5px;
      color: #64748b;
      line-height: 1.55;
      border-top: 1px solid var(--line);
      padding-top: 16px;
      margin: 28px 0 0 0;
    }}
    .disclaimer {{
      background: #fff8f8;
      border: 1px solid #fed7d7;
      border-left: 4px solid var(--brand);
      padding: 16px 20px;
      border-radius: 6px;
      font-size: 12px;
      color: #742a2a;
      line-height: 1.6;
      margin: 36px 0;
    }}
    .footer {{
      text-align: center;
      padding: 28px;
      font-size: 12px;
      color: var(--text-muted);
      border-top: 1px solid var(--line);
      background: var(--surface);
    }}
  </style>
</head>
<body>

  <div class="header">
    <div class="header-inner">
      <div class="header-brand">
        <div class="brand-mark">
          <img src="{logo_data_uri}" alt="SiteSurveyor Logo" class="brand-logo" />
        </div>
        <div>
          <div class="subtitle">An Eineva Labs product &bull; Autonomous Earth Observation Intelligence</div>
          <h1>SiteSurveyor AI <span class="header-badge">Executive Dossier</span></h1>
        </div>
      </div>
      <div class="header-client">
        <div>Client: <strong>{client_name}</strong></div>
        <div>Property: <strong>{client_address}</strong></div>
      </div>
    </div>
  </div>

  <div class="meta-bar">
    <div class="meta-item"><strong>GPS Latitude:</strong> <span>{latitude_label}</span></div>
    <div class="meta-item"><strong>GPS Longitude:</strong> <span>{longitude_label}</span></div>
    <div class="meta-item"><strong>Datum / CRS:</strong> <span>WGS 84 / UTM {zone_label} (EPSG:{cfg.EPSG})</span></div>
    <div class="meta-item"><strong>Resolution:</strong> <span>30m Multi-Sensor Grid</span></div>
    <div class="meta-item"><strong>Generated:</strong> <span>{dossier.get('generated_at')}</span></div>
  </div>

  <div class="container">

    {status_banner}

    <!-- Executive Multi-Criteria Scorecard -->
    <div class="section-title">1. Multi-Criteria Site Scorecard (Target Property)</div>
    <div class="note">
      <strong>How to read these numbers:</strong> each score is a percentile rank within this
      survey area, not an absolute measurement. A 60 means the target cell ranks above 60% of
      the surrounding AOI; two separate surveys are not comparable with each other.
    </div>
    <div class="scorecard-grid">

      <!-- Groundwater -->
      <div class="card card--water">
        <h3>Groundwater Potential</h3>
        <div class="big-score" style="color: {score_color(gw.get('cell_score'))};">{gw.get('cell_score', 'N/A')}</div>
        <span class="score-badge" style="background: {score_color(gw.get('cell_score'))};">{gw.get('cell_class', 'Unknown')}</span>
        <div class="detail-line"><strong>150m Parcel Mean:</strong> <span class="mono">{gw.get('parcel_150m_score', 'N/A')}/100</span> ({gw.get('parcel_150m_class', 'N/A')})</div>
        <div class="detail-line"><strong>Top Drilling Site:</strong> <span class="mono">{cand(gw, 'primary_borehole_candidate').get('distance_km', 'N/A')} km</span> away</div>
      </div>

      <!-- Minerals -->
      <div class="card card--mineral">
        <h3>Mineral Prospectivity</h3>
        <div class="big-score" style="color: {score_color(minerals.get('cell_score'))};">{minerals.get('cell_score', 'N/A')}</div>
        <span class="score-badge" style="background: {score_color(minerals.get('cell_score'))};">{minerals.get('cell_class', 'Unknown')}</span>
        <div class="detail-line"><strong>150m Parcel Mean:</strong> <span class="mono">{minerals.get('parcel_150m_score', 'N/A')}/100</span> ({minerals.get('parcel_150m_class', 'N/A')})</div>
        <div class="detail-line"><strong>Nearest Target:</strong> <span class="mono">{cand(minerals, 'primary_mineral_target').get('distance_km', 'N/A')} km</span> away</div>
      </div>

      <!-- Soil & Land -->
      <div class="card card--soil">
        <h3>Land & Soil Capability</h3>
        <div class="big-score" style="color: {score_color(soil.get('cell_score'))};">{soil.get('cell_score', 'N/A')}</div>
        <span class="score-badge" style="background: {score_color(soil.get('cell_score'))};">{soil.get('cell_class', 'Unknown')}</span>
        <div class="detail-line"><strong>150m Parcel Mean:</strong> <span class="mono">{soil.get('parcel_150m_score', 'N/A')}/100</span> ({soil.get('parcel_150m_class', 'N/A')})</div>
        <div class="detail-line"><strong>Prime Land Zone:</strong> <span class="mono">{cand(soil, 'primary_agricultural_zone').get('distance_km', 'N/A')} km</span> away</div>
      </div>

      <!-- Hazard & Risk -->
      <div class="card card--hazard">
        <h3>Site Safety Index</h3>
        <div class="big-score" style="color: {score_color(haz.get('safety_score'))};">{haz.get('safety_score', 'N/A')}</div>
        <span class="score-badge" style="background: {hazard_color(haz.get('hazard_score'))};">Hazard: {haz.get('hazard_score', 'N/A')}/100</span>
        <div class="detail-line"><strong>Classification:</strong> {haz.get('hazard_class', 'N/A')}</div>
        <div class="detail-line"><strong>Safest Building Site:</strong> <span class="mono">{cand(haz, 'primary_safe_build_site').get('distance_km', 'N/A')} km</span> away</div>
      </div>

    </div>

    <!-- Actionable GPS Recommendations Table -->
    <div class="section-title">2. Prioritised Field Verification Coordinates (Top Ranked per Category)</div>
    <table class="target-table">
      <thead>
        <tr>
          <th>Category</th>
          <th>Rank #</th>
          <th>GPS Latitude</th>
          <th>GPS Longitude</th>
          <th>Distance from Site</th>
          <th>Score</th>
          <th>Field Verification Action</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><strong style="color:var(--water);">Groundwater Siting</strong></td>
          <td><span class="mono">#1 Candidate</span></td>
          <td class="mono">{cand(gw, 'primary_borehole_candidate').get('latitude', 'N/A')}</td>
          <td class="mono">{cand(gw, 'primary_borehole_candidate').get('longitude', 'N/A')}</td>
          <td class="mono">{cand(gw, 'primary_borehole_candidate').get('distance_km', 'N/A')} km</td>
          <td><strong class="mono">{cand(gw, 'primary_borehole_candidate').get('potential_score', 'N/A')}/100</strong></td>
          <td>Vertical Electrical Sounding (VES) resistivity verification</td>
        </tr>
        <tr>
          <td><strong style="color:var(--mineral);">Mineral Exploration</strong></td>
          <td><span class="mono">#1 Target</span></td>
          <td class="mono">{cand(minerals, 'primary_mineral_target').get('latitude', 'N/A')}</td>
          <td class="mono">{cand(minerals, 'primary_mineral_target').get('longitude', 'N/A')}</td>
          <td class="mono">{cand(minerals, 'primary_mineral_target').get('distance_km', 'N/A')} km</td>
          <td><strong class="mono">{cand(minerals, 'primary_mineral_target').get('prospectivity_score', 'N/A')}/100</strong></td>
          <td>Ground geological mapping & soil geochemical sampling</td>
        </tr>
        <tr>
          <td><strong style="color:var(--soil);">Soil & Agriculture</strong></td>
          <td><span class="mono">#1 Zone</span></td>
          <td class="mono">{cand(soil, 'primary_agricultural_zone').get('latitude', 'N/A')}</td>
          <td class="mono">{cand(soil, 'primary_agricultural_zone').get('longitude', 'N/A')}</td>
          <td class="mono">{cand(soil, 'primary_agricultural_zone').get('distance_km', 'N/A')} km</td>
          <td><strong class="mono">{cand(soil, 'primary_agricultural_zone').get('capability_score', 'N/A')}/100</strong></td>
          <td>Agronomic soil profile test & pH analysis</td>
        </tr>
        <tr>
          <td><strong style="color:var(--hazard);">Safest Building Site</strong></td>
          <td><span class="mono">#1 Safe Zone</span></td>
          <td class="mono">{cand(haz, 'primary_safe_build_site').get('latitude', 'N/A')}</td>
          <td class="mono">{cand(haz, 'primary_safe_build_site').get('longitude', 'N/A')}</td>
          <td class="mono">{cand(haz, 'primary_safe_build_site').get('distance_km', 'N/A')} km</td>
          <td><strong class="mono">{cand(haz, 'primary_safe_build_site').get('safety_score', 'N/A')}/100</strong></td>
          <td>Geotechnical soil compaction & foundation investigation</td>
        </tr>
      </tbody>
    </table>

    <!-- Satellite Intelligence Cartography -->
    <div class="section-title">3. High-Resolution Satellite Evidence & Siting Maps</div>
    <div class="maps-grid">
      {maps_html}
    </div>

    <!-- Data attribution -->
    <div class="attribution">
      <strong>Data attribution:</strong> Copernicus Sentinel-2 and Copernicus DEM 30m via
      Digital Earth Africa (CC BY 4.0); ESA WorldCover (CC BY 4.0); JAXA ALOS PALSAR mosaic
      (&copy; JAXA/METI); Landsat imagery courtesy of USGS/NASA; CHIRPS precipitation courtesy
      of the Climate Hazards Center, UC Santa Barbara. Screening output produced by
      SiteSurveyor AI &mdash; Eineva Labs.
    </div>

    <!-- Regulatory / Engineering Disclaimer -->
    <div class="disclaimer">
      <strong>SCREENING-LEVEL INTELLIGENCE DISCLAIMER:</strong><br/>
      This dossier is produced by SiteSurveyor AI using autonomous multi-sensor satellite Earth observation
      (Copernicus Sentinel-2, Copernicus DEM 30m, JAXA ALOS PALSAR, ESA WorldCover, and CHIRPS precipitation).
      All findings represent pre-feasibility, screening-level probability zoning. This analysis is not a substitute
      for certified geotechnical, hydrogeological, or mining engineering field investigations. Ground geophysical
      confirmation (VES / ERT resistivity, soil assays, and structural ground truthing) is mandatory prior to drilling,
      excavation, construction, or commercial investment.
    </div>

  </div>

  <div class="footer">
    SiteSurveyor AI &bull; Produced by <strong>{cfg.ANALYST}</strong> for <strong>{client_name}</strong> &bull; An Eineva Labs product &bull; All Rights Reserved.
  </div>

</body>
</html>
"""
    return html


if __name__ == "__main__":
    generate_site_dossier()

