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
from src import fetch_data


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


def _survey_identity(sections: list[dict | None]) -> dict | None:
    """The site and client the loaded category files were actually produced for.

    Every summary carries the coordinates it was generated from, so the dossier can name
    the ground it is reporting on instead of trusting whichever AOI the process happens
    to be holding right now.
    """
    for data in sections:
        if not isinstance(data, dict):
            continue
        coords = data.get("target_coordinates")
        if isinstance(coords, dict):
            lat, lon = coords.get("latitude"), coords.get("longitude")
        else:
            lat, lon = data.get("target_lat"), data.get("target_lon")
        numeric = isinstance(lat, (int, float)) and not isinstance(lat, bool)
        numeric = numeric and isinstance(lon, (int, float)) and not isinstance(lon, bool)
        if numeric:
            return {
                "latitude": float(lat),
                "longitude": float(lon),
                "client": data.get("client") or None,
                "address": data.get("address") or None,
            }
    return None


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

    # A restarted engine holds its compiled default AOI while the survey files on disk
    # still belong to the previous client. Reporting the surveyed site rather than the
    # live config is what stops one client's coordinates heading another client's numbers.
    identity = _survey_identity([water_data, minerals_data, soil_data, hazard_data])
    if identity:
        if (round(identity["latitude"], 5), round(identity["longitude"], 5)) != (
                round(cfg.TARGET_LAT, 5), round(cfg.TARGET_LON, 5)):
            print(f"  [!] Survey files belong to ({identity['latitude']:.5f}, {identity['longitude']:.5f})"
                  f" [{identity['client'] or 'unnamed'}], not the live config target.")
    else:
        identity = {"latitude": cfg.TARGET_LAT, "longitude": cfg.TARGET_LON,
                    "client": cfg.CLIENT, "address": cfg.CLIENT_ADDRESS}

    # 1. Build Master JSON Dossier
    dossier = {
        "title": "SiteSurveyor AI Executive Site Intelligence Dossier",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "client": identity["client"] or cfg.CLIENT,
        "address": identity["address"] or cfg.CLIENT_ADDRESS,
        "analyst_organization": cfg.ANALYST,
        "target_coordinates": {
            "latitude": identity["latitude"],
            "longitude": identity["longitude"],
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

    def number(value):
        """A real measurement, or None.

        ``dict.get(key, "N/A")`` still returns None when the key exists holding a null,
        and a survey writes exactly that when a category ran but scored nothing at the
        target cell. Left raw, the client document prints the word "None" as a score.
        """
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return float(value)

    def score(value):
        v = number(value)
        if v is None:
            return "N/A"
        return f"{v:.1f}".rstrip("0").rstrip(".")

    def out_of(value):
        """A score written as "62.4/100", or N/A -- never the fragment "N/A/100"."""
        v = number(value)
        return "N/A" if v is None else f"{score(v)}/100"

    def distance(value):
        v = number(value)
        return "N/A" if v is None else f"{v:.2f} km"

    def coordinate(value, digits=5):
        v = number(value)
        return "N/A" if v is None else f"{v:.{digits}f}"

    def label(value, fallback="Not classified"):
        return _escape(str(value)) if value else fallback

    def band(value, lower_is_better=False):
        """One colour per score band, for both the headline number and its badge.

        The ramp is shared by the 38px headline score and the 11px badge under it. A
        mid-tone like #10b981 clears neither 4.5:1 as text on white nor 4.5:1 with white
        type inside it, so every step here is dark enough to do both jobs at once.
        """
        v = number(value)
        if v is None:
            return "#475569"
        if lower_is_better:
            if v <= 30:
                return "#047857"
            if v <= 50:
                return "#92400e"
            return "#b91c1c"
        if v >= 75:
            return "#047857"
        if v >= 55:
            return "#92400e"
        if v >= 40:
            return "#9a3412"
        return "#b91c1c"

    sc = dossier.get("executive_scorecard", {})
    gw = sc.get("groundwater", {})
    minerals = sc.get("minerals", {})
    soil = sc.get("soil_land", {})
    haz = sc.get("hazard_safety", {})

    # Client, address and coordinates are caller-supplied and this document is served
    # same-origin, so they are escaped before interpolation. Unescaped, a client name
    # containing a script tag executed for the next visitor of /api/report.
    # They come from the dossier rather than cfg: the module globals may belong to a
    # different survey than the files these numbers were read from.
    client_name = _escape(dossier.get("client") or cfg.CLIENT or "Client")
    client_address = _escape(dossier.get("address") or cfg.CLIENT_ADDRESS or "")
    property_line = f'<div>Property: <strong>{client_address}</strong></div>' if client_address else ""
    coords = dossier.get("target_coordinates") or {}
    site_lat = number(coords.get("latitude"))
    site_lon = number(coords.get("longitude"))
    if site_lat is None or site_lon is None:
        site_lat, site_lon = cfg.TARGET_LAT, cfg.TARGET_LON
    latitude_label = f"{abs(site_lat):.5f}&deg; {'N' if site_lat >= 0 else 'S'}"
    longitude_label = f"{abs(site_lon):.5f}&deg; {'E' if site_lon >= 0 else 'W'}"
    utm_zone = int((site_lon + 180.0) // 6.0) + 1
    epsg = (32700 + utm_zone) if site_lat < 0 else (32600 + utm_zone)
    zone_label = f"{utm_zone}{'N' if site_lat >= 0 else 'S'}"

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
        ("Category 1: Groundwater Potential Zones (GWPZ)", "groundwater_potential_map.png",
         "Map of the survey area shaded by groundwater potential class, with the client target "
         "starred and each ranked drilling candidate labelled by rank."),
        ("Groundwater Local Siting Zoom (5x5 km)", "site_zoom_map.png",
         "Five by five kilometre zoom around the client property, plotting candidate borehole "
         "positions as an offset from the target in kilometres."),
        ("Category 2: Mineral Prospectivity & Shear Zones", "mineral_prospectivity_map.png",
         "Map of the survey area shaded by gold and shear-system prospectivity class, with the "
         "client target starred and ranked exploration targets labelled by rank."),
        ("Category 3: Soil & Land Capability Zoning", "soil_capability_map.png",
         "Map of the survey area shaded by soil and land capability class, with the client target "
         "starred and ranked candidate zones labelled by rank."),
        ("Category 5: Natural Hazard & Risk Zoning", "hazard_risk_map.png",
         "Map of the survey area shaded by composite natural hazard risk class, with the client "
         "target starred and the safest ranked build sites labelled by rank."),
        ("Site Safety & Hazard Zoom (5x5 km)", "site_hazard_zoom.png",
         "Five by five kilometre zoom around the client property, plotting the safest build sites "
         "as an offset from the target in kilometres."),
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
                f'<p class="map-missing">Map not embedded: {img_note}.</p></div>')
    maps_html = "\n      ".join(map_panels)

    # Credited from the sidecars the fetch left in this AOI, not from the registry defaults:
    # a dossier that names Copernicus DEM while the scores came from SRTM is a false
    # attribution on a document someone signs off on.
    used_sources = fetch_data.used_sources()
    dea_credit = ", ".join(_escape(v["label"]) + " (CC BY 4.0)"
                           for v in used_sources["selectable"].values())
    and_credit = f" and {dea_credit}" if dea_credit else ""

    # Coordinates are generated from the survey output instead of hardcoding each #1 pick.
    # A client acting on one point has no fallback if that spot is already spoken for, and
    # a category that ranked nothing must not render a phantom "#1 Candidate" at N/A.
    # The category tints are darker than the domain hues: the bright cyan and amber used for
    # borders and badges dissolve to ~2.2:1 as small text on a white page.
    table_specs = [
        ("Groundwater Siting", "water", "candidate_sites", "#0369a1", "Candidate",
         "Vertical Electrical Sounding (VES) resistivity verification"),
        ("Mineral Exploration", "minerals", "candidate_targets", "#a16207", "Target",
         "Ground geological mapping &amp; soil geochemical sampling"),
        ("Soil &amp; Agriculture", "soil_land", "candidate_areas", "#047857", "Zone",
         "Agronomic soil profile test &amp; pH analysis"),
        ("Safest Building Site", "hazard_safety", "safest_candidate_sites", "#be123c", "Safe Zone",
         "Geotechnical soil compaction &amp; foundation investigation"),
    ]
    categories = dossier.get("categories", {}) or {}
    coord_rows = []
    for name, key, list_key, tint, noun, action in table_specs:
        ranked = [c for c in ((categories.get(key) or {}).get(list_key) or []) if isinstance(c, dict)][:3]
        if not ranked:
            coord_rows.append(
                f'        <tr>\n'
                f'          <td><strong style="color:{tint};">{name}</strong></td>\n'
                f'          <td colspan="5" class="empty-row">No candidate ranked above the screening '
                f'threshold for this category.</td>\n'
                f'          <td>{action}</td>\n'
                f'        </tr>'
            )
            continue
        span = len(ranked)
        for index, item in enumerate(ranked):
            cells = []
            if index == 0:
                cells.append(f'          <td rowspan="{span}"><strong style="color:{tint};">{name}</strong></td>')
            rank = number(item.get("rank"))
            cells.append(f'          <td><span class="mono">{"#" + str(int(rank)) if rank is not None else "Unranked"} {noun}</span></td>')
            cells.append(f'          <td class="mono">{coordinate(item.get("latitude"))}</td>')
            cells.append(f'          <td class="mono">{coordinate(item.get("longitude"))}</td>')
            cells.append(f'          <td class="mono">{distance(item.get("distance_from_target_km"))}</td>')
            value = item.get("potential_score")
            cells.append(f'          <td><strong class="mono" style="color: {band(value)};">{out_of(value)}</strong></td>')
            if index == 0:
                cells.append(f'          <td rowspan="{span}">{action}</td>')
            coord_rows.append("        <tr>\n" + "\n".join(cells) + "\n        </tr>")
    coord_rows_html = "\n".join(coord_rows)

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
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <meta name="description" content="SiteSurveyor AI executive site intelligence dossier for {client_name}.">
  <title>{client_name} &mdash; SiteSurveyor AI Site Intelligence Dossier</title>
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
      --text-quiet: #475569;
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
      -webkit-text-size-adjust: 100%;
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
      min-width: 0;
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
      color: #f87171;
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
    .table-wrap {{
      border: 1px solid var(--line);
      border-radius: 10px;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
      margin-bottom: 35px;
      /* Seven columns cannot breathe in 390px; a scrollable sheet keeps every
         coordinate legible instead of crushing them into a wrapped blur. */
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
    }}
    .target-table {{
      width: 100%;
      min-width: 46rem;
      border-collapse: collapse;
      background: var(--surface);
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
      white-space: nowrap;
    }}
    .target-table td {{
      padding: 12px 14px;
      border-top: 1px solid var(--line);
      color: var(--text);
      vertical-align: top;
    }}
    .target-table td.mono, .target-table td .mono {{
      white-space: nowrap;
    }}
    .target-table tbody tr:first-child td {{
      border-top: none;
    }}
    /* No row hover: the category and its field action are rowspanned across the three
       candidates under them, so a hovered row would light only part of its own group. */
    .target-table .empty-row {{
      color: var(--text-muted);
      font-style: italic;
    }}

    /* Maps Grid */
    .maps-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(min(100%, 480px), 1fr));
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
    .map-missing {{
      color: #b91c1c;
      font-size: 12px;
      margin: 2px 0;
    }}

    /* Banners & Notes */
    .status-banner {{
      background: #fffbeb;
      border: 1px solid #fde68a;
      border-left: 4px solid var(--mineral);
      border-radius: 6px;
      padding: 14px 18px;
      font-size: 12.5px;
      color: #92400e;
      margin-bottom: 25px;
    }}
    .note {{
      font-size: 12px;
      color: var(--text-quiet);
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

    /* The dossier is read on a phone in the field and printed for the file, so both are
       designed for rather than left to shrink. */
    @media (max-width: 720px) {{
      .header {{ padding: 24px 20px; }}
      .header-inner {{ flex-direction: column; align-items: flex-start; gap: 16px; }}
      .header-client {{ padding: 10px 14px; max-width: 100%; min-width: 0; overflow-wrap: anywhere; }}
      .header h1 {{ font-size: 20px; letter-spacing: -0.3px; }}
      .header .subtitle {{ font-size: 11px; }}
      .meta-bar {{ padding: 12px 20px; justify-content: flex-start; gap: 10px 22px; }}
      .meta-item {{ min-width: 0; overflow-wrap: anywhere; }}
      .container {{ margin: 22px auto; padding: 0 14px; }}
      .section-title {{ font-size: 16px; margin: 30px 0 14px 0; }}
      .scorecard-grid, .maps-grid {{ gap: 14px; }}
      .card, .map-box {{ padding: 16px; }}
      .footer {{ padding: 22px 14px; }}
    }}

    @media print {{
      @page {{ margin: 14mm; }}
      body {{ background: #ffffff; }}
      .header, .meta-bar, .card, .map-box, .score-badge, .status-banner,
      .disclaimer, .note, .table-wrap, .target-table th {{
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
      }}
      .card, .map-box, .status-banner, .disclaimer, .attribution, .note {{ break-inside: avoid; }}
      .section-title {{ break-after: avoid; }}
      .container {{ max-width: none; margin: 16px 0; padding: 0; }}
      .header {{ padding: 22px 24px; }}
      .table-wrap {{ overflow: visible; box-shadow: none; }}
      .target-table {{ min-width: 0; }}
      .maps-grid {{ grid-template-columns: 1fr 1fr; }}
      .map-box img {{ width: auto; max-width: 100%; max-height: 105mm; margin: 0 auto; }}
      .card, .map-box, .table-wrap {{ box-shadow: none; }}
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
        {property_line}
      </div>
    </div>
  </div>

  <div class="meta-bar">
    <div class="meta-item"><strong>GPS Latitude:</strong> <span>{latitude_label}</span></div>
    <div class="meta-item"><strong>GPS Longitude:</strong> <span>{longitude_label}</span></div>
    <div class="meta-item"><strong>Datum / CRS:</strong> <span>WGS 84 / UTM {zone_label} (EPSG:{epsg})</span></div>
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
        <div class="big-score" style="color: {band(gw.get('cell_score'))};">{score(gw.get('cell_score'))}</div>
        <span class="score-badge" style="background: {band(gw.get('cell_score'))};">{label(gw.get('cell_class'))}</span>
        <div class="detail-line"><strong>150m Parcel Mean:</strong> <span class="mono">{out_of(gw.get('parcel_150m_score'))}</span> ({label(gw.get('parcel_150m_class'))})</div>
        <div class="detail-line"><strong>Top Drilling Site:</strong> <span class="mono">{distance(cand(gw, 'primary_borehole_candidate').get('distance_km'))}</span> away</div>
      </div>

      <!-- Minerals -->
      <div class="card card--mineral">
        <h3>Mineral Prospectivity</h3>
        <div class="big-score" style="color: {band(minerals.get('cell_score'))};">{score(minerals.get('cell_score'))}</div>
        <span class="score-badge" style="background: {band(minerals.get('cell_score'))};">{label(minerals.get('cell_class'))}</span>
        <div class="detail-line"><strong>150m Parcel Mean:</strong> <span class="mono">{out_of(minerals.get('parcel_150m_score'))}</span> ({label(minerals.get('parcel_150m_class'))})</div>
        <div class="detail-line"><strong>Nearest Target:</strong> <span class="mono">{distance(cand(minerals, 'primary_mineral_target').get('distance_km'))}</span> away</div>
      </div>

      <!-- Soil & Land -->
      <div class="card card--soil">
        <h3>Land &amp; Soil Capability</h3>
        <div class="big-score" style="color: {band(soil.get('cell_score'))};">{score(soil.get('cell_score'))}</div>
        <span class="score-badge" style="background: {band(soil.get('cell_score'))};">{label(soil.get('cell_class'))}</span>
        <div class="detail-line"><strong>150m Parcel Mean:</strong> <span class="mono">{out_of(soil.get('parcel_150m_score'))}</span> ({label(soil.get('parcel_150m_class'))})</div>
        <div class="detail-line"><strong>Prime Land Zone:</strong> <span class="mono">{distance(cand(soil, 'primary_agricultural_zone').get('distance_km'))}</span> away</div>
      </div>

      <!-- Hazard & Risk -->
      <div class="card card--hazard">
        <h3>Site Safety Index</h3>
        <div class="big-score" style="color: {band(haz.get('safety_score'))};">{score(haz.get('safety_score'))}</div>
        <span class="score-badge" style="background: {band(haz.get('hazard_score'), lower_is_better=True)};">Hazard: {out_of(haz.get('hazard_score'))}</span>
        <div class="detail-line"><strong>Classification:</strong> {label(haz.get('hazard_class'))}</div>
        <div class="detail-line"><strong>Safest Building Site:</strong> <span class="mono">{distance(cand(haz, 'primary_safe_build_site').get('distance_km'))}</span> away</div>
      </div>

    </div>

    <!-- Actionable GPS Recommendations Table -->
    <div class="section-title">2. Prioritised Field Verification Coordinates (Top Ranked per Category)</div>
    <div class="note">
      <strong>Three ranked points per category, not one:</strong> candidates are ordered within
      this survey area, so work the list top-down &mdash; the second and third are the fallbacks
      when the highest-scoring cell is already spoken for. On a phone, swipe the table sideways
      to reach the remaining columns.
    </div>
    <div class="table-wrap">
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
{coord_rows_html}
      </tbody>
    </table>
    </div>

    <!-- Satellite Intelligence Cartography -->
    <div class="section-title">3. High-Resolution Satellite Evidence & Siting Maps</div>
    <div class="maps-grid">
      {maps_html}
    </div>

    <!-- Data attribution -->
    <div class="attribution">
      <strong>Data attribution:</strong> Copernicus Sentinel-2{and_credit} via
      Digital Earth Africa; JAXA ALOS PALSAR mosaic
      (&copy; JAXA/METI); Landsat imagery courtesy of USGS/NASA; CHIRPS precipitation courtesy
      of the Climate Hazards Center, UC Santa Barbara. Screening output produced by
      SiteSurveyor AI &mdash; Eineva Labs.
    </div>

    <!-- Regulatory / Engineering Disclaimer -->
    <div class="disclaimer">
      <strong>SCREENING-LEVEL INTELLIGENCE DISCLAIMER:</strong><br/>
      This dossier is produced by SiteSurveyor AI using autonomous multi-sensor satellite Earth
      observation: elevation, land cover, optical and radar backscatter, and precipitation, each
      named in the attribution above.
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

