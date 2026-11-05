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
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src.config as cfg


def _load_json_safe(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _img_to_base64_src(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    except Exception:
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

    water_data = _load_json_safe(cfg.OUT / "summary.json")
    minerals_data = _load_json_safe(cfg.OUT / "mineral_summary.json")
    soil_data = _load_json_safe(cfg.OUT / "soil_summary.json")
    hazard_data = _load_json_safe(cfg.OUT / "hazard_summary.json")

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
    sc = dossier.get("executive_scorecard", {})
    gw = sc.get("groundwater", {})
    minerals = sc.get("minerals", {})
    soil = sc.get("soil_land", {})
    haz = sc.get("hazard_safety", {})

    # Convert map images to base64 for complete offline portability
    img_gw_map = _img_to_base64_src(cfg.OUT / "groundwater_potential_map.png")
    img_gw_zoom = _img_to_base64_src(cfg.OUT / "site_zoom_map.png")
    img_min_map = _img_to_base64_src(cfg.OUT / "mineral_prospectivity_map.png")
    img_soil_map = _img_to_base64_src(cfg.OUT / "soil_capability_map.png")
    img_haz_map = _img_to_base64_src(cfg.OUT / "hazard_risk_map.png")
    img_haz_zoom = _img_to_base64_src(cfg.OUT / "site_hazard_zoom.png")

    def score_color(val):
        if val is None:
            return "#777777"
        if val >= 75:
            return "#1a9850"
        elif val >= 55:
            return "#91cf60"
        elif val >= 40:
            return "#f49d37"
        else:
            return "#d73027"

    def hazard_color(val):
        if val is None:
            return "#777777"
        if val <= 30:
            return "#1a9850"
        elif val <= 50:
            return "#f49d37"
        else:
            return "#d73027"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>SiteSurveyor AI — Executive Site Intelligence Dossier</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      margin: 0;
      padding: 0;
      background-color: #f7f9fa;
      color: #2c3e50;
      line-height: 1.6;
    }}
    .header {{
      background: linear-gradient(135deg, {cfg.BRAND_COLOR} 0%, #062b3b 100%);
      color: #ffffff;
      padding: 35px 50px;
    }}
    .header h1 {{
      margin: 0 0 10px 0;
      font-size: 28px;
      letter-spacing: -0.5px;
    }}
    .header .subtitle {{
      font-size: 14px;
      opacity: 0.85;
      text-transform: uppercase;
      letter-spacing: 1px;
    }}
    .meta-bar {{
      background: #ffffff;
      border-bottom: 1px solid #e1e8ed;
      padding: 15px 50px;
      display: flex;
      flex-wrap: wrap;
      gap: 30px;
      font-size: 13px;
    }}
    .meta-item strong {{
      color: {cfg.BRAND_COLOR};
    }}
    .container {{
      max-width: 1200px;
      margin: 30px auto;
      padding: 0 30px;
    }}
    .scorecard-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 20px;
      margin-bottom: 35px;
    }}
    .card {{
      background: #ffffff;
      border-radius: 8px;
      padding: 24px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.06);
      border-top: 4px solid {cfg.BRAND_COLOR};
    }}
    .card h3 {{
      margin: 0 0 15px 0;
      font-size: 15px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: #555;
    }}
    .big-score {{
      font-size: 42px;
      font-weight: 800;
      line-height: 1;
      margin-bottom: 8px;
    }}
    .score-badge {{
      display: inline-block;
      padding: 3px 10px;
      border-radius: 12px;
      font-size: 12px;
      font-weight: 600;
      color: #ffffff;
      margin-bottom: 12px;
    }}
    .detail-line {{
      font-size: 12px;
      color: #666;
      border-top: 1px solid #f0f0f0;
      padding-top: 8px;
      margin-top: 8px;
    }}
    .section-title {{
      font-size: 20px;
      font-weight: 700;
      color: {cfg.BRAND_COLOR};
      margin: 40px 0 20px 0;
      padding-bottom: 8px;
      border-bottom: 2px solid {cfg.BRAND_COLOR};
    }}
    .target-table {{
      width: 100%;
      border-collapse: collapse;
      background: #ffffff;
      border-radius: 8px;
      overflow: hidden;
      box-shadow: 0 2px 8px rgba(0,0,0,0.06);
      margin-bottom: 30px;
      font-size: 13px;
    }}
    .target-table th {{
      background: #f1f5f9;
      color: #334155;
      text-align: left;
      padding: 12px 16px;
      font-weight: 600;
    }}
    .target-table td {{
      padding: 12px 16px;
      border-top: 1px solid #f1f5f9;
    }}
    .maps-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
      gap: 25px;
      margin-bottom: 35px;
    }}
    .map-box {{
      background: #ffffff;
      border-radius: 8px;
      padding: 15px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }}
    .map-box h4 {{
      margin: 0 0 10px 0;
      font-size: 14px;
      color: {cfg.BRAND_COLOR};
    }}
    .map-box img {{
      width: 100%;
      height: auto;
      border-radius: 4px;
      border: 1px solid #e1e8ed;
    }}
    .disclaimer {{
      background: #fff8e6;
      border-left: 4px solid #f49d37;
      padding: 18px 22px;
      border-radius: 4px;
      font-size: 12px;
      color: #7a5210;
      margin: 40px 0;
    }}
    .footer {{
      text-align: center;
      padding: 30px;
      font-size: 12px;
      color: #888;
      border-top: 1px solid #e1e8ed;
      background: #ffffff;
    }}
  </style>
</head>
<body>

  <div class="header">
    <div class="subtitle">Eineva Labs &bull; Autonomous Earth Observation Intelligence</div>
    <h1>SiteSurveyor AI &mdash; Executive Site Intelligence Dossier</h1>
    <div>Client: <strong>{cfg.CLIENT}</strong> | Property: {cfg.CLIENT_ADDRESS}</div>
  </div>

  <div class="meta-bar">
    <div class="meta-item"><strong>GPS Latitude:</strong> {cfg.TARGET_LAT:.5f}&deg; S</div>
    <div class="meta-item"><strong>GPS Longitude:</strong> {cfg.TARGET_LON:.5f}&deg; E</div>
    <div class="meta-item"><strong>Datum / CRS:</strong> WGS 84 / UTM Zone {cfg.UTM_ZONE} (EPSG:{cfg.EPSG})</div>
    <div class="meta-item"><strong>Resolution:</strong> 30-metre synchronized satellite grid</div>
    <div class="meta-item"><strong>Generated:</strong> {dossier.get('generated_at')}</div>
  </div>

  <div class="container">

    <!-- Executive Multi-Criteria Scorecard -->
    <div class="section-title">1. Multi-Criteria Site Scorecard (Target Property)</div>
    <div class="scorecard-grid">

      <!-- Groundwater -->
      <div class="card">
        <h3>Groundwater Potential</h3>
        <div class="big-score" style="color: {score_color(gw.get('cell_score'))};">{gw.get('cell_score', 'N/A')}</div>
        <span class="score-badge" style="background: {score_color(gw.get('cell_score'))};">{gw.get('cell_class', 'Unknown')}</span>
        <div class="detail-line"><strong>150m Parcel Mean:</strong> {gw.get('parcel_150m_score', 'N/A')}/100 ({gw.get('parcel_150m_class', 'N/A')})</div>
        <div class="detail-line"><strong>Top Drilling Site:</strong> {gw.get('primary_borehole_candidate', {}).get('distance_km', 'N/A')} km away</div>
      </div>

      <!-- Minerals -->
      <div class="card">
        <h3>Mineral Prospectivity</h3>
        <div class="big-score" style="color: {score_color(minerals.get('cell_score'))};">{minerals.get('cell_score', 'N/A')}</div>
        <span class="score-badge" style="background: {score_color(minerals.get('cell_score'))};">{minerals.get('cell_class', 'Unknown')}</span>
        <div class="detail-line"><strong>150m Parcel Mean:</strong> {minerals.get('parcel_150m_score', 'N/A')}/100 ({minerals.get('parcel_150m_class', 'N/A')})</div>
        <div class="detail-line"><strong>Nearest Target:</strong> {minerals.get('primary_mineral_target', {}).get('distance_km', 'N/A')} km away</div>
      </div>

      <!-- Soil & Land -->
      <div class="card">
        <h3>Land & Soil Capability</h3>
        <div class="big-score" style="color: {score_color(soil.get('cell_score'))};">{soil.get('cell_score', 'N/A')}</div>
        <span class="score-badge" style="background: {score_color(soil.get('cell_score'))};">{soil.get('cell_class', 'Unknown')}</span>
        <div class="detail-line"><strong>150m Parcel Mean:</strong> {soil.get('parcel_150m_score', 'N/A')}/100 ({soil.get('parcel_150m_class', 'N/A')})</div>
        <div class="detail-line"><strong>Prime Land Zone:</strong> {soil.get('primary_agricultural_zone', {}).get('distance_km', 'N/A')} km away</div>
      </div>

      <!-- Hazard & Risk -->
      <div class="card">
        <h3>Site Safety Index</h3>
        <div class="big-score" style="color: {score_color(haz.get('safety_score'))};">{haz.get('safety_score', 'N/A')}</div>
        <span class="score-badge" style="background: {hazard_color(haz.get('hazard_score'))};">Hazard: {haz.get('hazard_score', 'N/A')}/100</span>
        <div class="detail-line"><strong>Classification:</strong> {haz.get('hazard_class', 'N/A')}</div>
        <div class="detail-line"><strong>Safest Building Site:</strong> {haz.get('primary_safe_build_site', {}).get('distance_km', 'N/A')} km away</div>
      </div>

    </div>

    <!-- Actionable GPS Recommendations Table -->
    <div class="section-title">2. Actionable Precision Field Coordinates (Top Ranked per Category)</div>
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
          <td><strong>Groundwater Siting</strong></td>
          <td>#1 Candidate</td>
          <td>{gw.get('primary_borehole_candidate', {}).get('latitude', 'N/A')}</td>
          <td>{gw.get('primary_borehole_candidate', {}).get('longitude', 'N/A')}</td>
          <td>{gw.get('primary_borehole_candidate', {}).get('distance_km', 'N/A')} km</td>
          <td><strong>{gw.get('primary_borehole_candidate', {}).get('potential_score', 'N/A')}/100</strong></td>
          <td>Vertical Electrical Sounding (VES) resistivity verification</td>
        </tr>
        <tr>
          <td><strong>Mineral Exploration</strong></td>
          <td>#1 Target</td>
          <td>{minerals.get('primary_mineral_target', {}).get('latitude', 'N/A')}</td>
          <td>{minerals.get('primary_mineral_target', {}).get('longitude', 'N/A')}</td>
          <td>{minerals.get('primary_mineral_target', {}).get('distance_km', 'N/A')} km</td>
          <td><strong>{minerals.get('primary_mineral_target', {}).get('prospectivity_score', 'N/A')}/100</strong></td>
          <td>Ground geological mapping & soil geochemical sampling</td>
        </tr>
        <tr>
          <td><strong>Soil & Agriculture</strong></td>
          <td>#1 Zone</td>
          <td>{soil.get('primary_agricultural_zone', {}).get('latitude', 'N/A')}</td>
          <td>{soil.get('primary_agricultural_zone', {}).get('longitude', 'N/A')}</td>
          <td>{soil.get('primary_agricultural_zone', {}).get('distance_km', 'N/A')} km</td>
          <td><strong>{soil.get('primary_agricultural_zone', {}).get('capability_score', 'N/A')}/100</strong></td>
          <td>Agronomic soil profile test & pH analysis</td>
        </tr>
        <tr>
          <td><strong>Safest Building Site</strong></td>
          <td>#1 Safe Zone</td>
          <td>{haz.get('primary_safe_build_site', {}).get('latitude', 'N/A')}</td>
          <td>{haz.get('primary_safe_build_site', {}).get('longitude', 'N/A')}</td>
          <td>{haz.get('primary_safe_build_site', {}).get('distance_km', 'N/A')} km</td>
          <td><strong>{haz.get('primary_safe_build_site', {}).get('safety_score', 'N/A')}/100</strong></td>
          <td>Geotechnical soil compaction & foundation investigation</td>
        </tr>
      </tbody>
    </table>

    <!-- Satellite Intelligence Cartography -->
    <div class="section-title">3. High-Resolution Satellite Evidence & Siting Maps</div>
    <div class="maps-grid">
      {f'<div class="map-box"><h4>Category 1: Groundwater Potential Zones (GWPZ)</h4><img src="{img_gw_map}" alt="Groundwater Map"/></div>' if img_gw_map else ''}
      {f'<div class="map-box"><h4>Groundwater Local Siting Zoom (5x5 km)</h4><img src="{img_gw_zoom}" alt="Groundwater Zoom"/></div>' if img_gw_zoom else ''}
      {f'<div class="map-box"><h4>Category 2: Mineral Prospectivity & Shear Zones</h4><img src="{img_min_map}" alt="Minerals Map"/></div>' if img_min_map else ''}
      {f'<div class="map-box"><h4>Category 3: Soil & Land Capability Zoning</h4><img src="{img_soil_map}" alt="Soil Map"/></div>' if img_soil_map else ''}
      {f'<div class="map-box"><h4>Category 5: Natural Hazard & Risk Zoning</h4><img src="{img_haz_map}" alt="Hazard Map"/></div>' if img_haz_map else ''}
      {f'<div class="map-box"><h4>Site Safety & Hazard Zoom (5x5 km)</h4><img src="{img_haz_zoom}" alt="Hazard Zoom"/></div>' if img_haz_zoom else ''}
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
    SiteSurveyor AI v2.0 &bull; Produced by <strong>{cfg.ANALYST}</strong> for <strong>{cfg.CLIENT}</strong> &bull; All Rights Reserved.
  </div>

</body>
</html>
"""
    return html


if __name__ == "__main__":
    generate_site_dossier()

