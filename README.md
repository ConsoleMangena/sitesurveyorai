# 🛰️ SiteSurveyor AI

**Autonomous Satellite Geospatial Intelligence Engine** by [Eineva Labs](https://eineva.com).

SiteSurveyor AI ingests multi-sensor Earth observation satellite data (Copernicus Sentinel-2, Copernicus DEM 30m, JAXA ALOS PALSAR, Landsat WOfS 1984–2024, ESA WorldCover, and CHIRPS precipitation) through multi-criteria decision analysis (AHP / MCDA) to deliver automated site screening, natural hazard due diligence, and precision GPS targeting.

---

## ⚡ Interfaces

SiteSurveyor AI can be operated via **two primary interfaces**:

1. **AI Agent Interface (Model Context Protocol / MCP)**: An AI agent (Claude, Gemini, Cursor, ChatGPT) connects directly and uses SiteSurveyor as native tools.
2. **Unified Command-Line Interface (CLI)**: For batch execution, local testing, and cartographic map generation.

---

## 🔌 AI Agent Integration (MCP)

SiteSurveyor AI is an official **Model Context Protocol (MCP)** server.

### 1. Connect to Claude Desktop or Cursor
Add this to your MCP configuration (`claude_desktop_config.json` or `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "SiteSurveyorAI": {
      "command": "python",
      "args": ["-m", "src.mcp_server"],
      "cwd": "c:\\Users\\THINKPAD\\Documents\\SiteSurveyorAI"
    }
  }
}
```

### 2. Tools Available to the Agent:
* `survey_site(latitude, longitude, categories)` — Full multi-domain site screening.
* `get_boreholes(latitude, longitude)` — Precision borehole drilling targets with VES advice.
* `get_minerals(latitude, longitude)` — Shear-zone gold prospectivity & hydrothermal alteration.
* `get_soil_capability(latitude, longitude)` — Agricultural suitability & erosion risk.
* `get_hazard_safety(latitude, longitude)` — Natural hazards (flood, slope failure, wildfire) and safest buildable sites.
* `get_executive_dossier()` — Master multi-criteria scorecard and portable HTML report.

*(For full details, see [`docs/MCP_GUIDE.md`](docs/MCP_GUIDE.md)).*

---

## 💻 CLI Usage

```bash
# Run all survey categories + generate executive HTML/JSON dossier:
python main.py --category all

# Run individual categories:
python main.py --category water       # Groundwater potential & borehole siting
python main.py --category minerals    # Shear-zone gold prospectivity screening
python main.py --category soil        # Soil capability & erosion risk
python main.py --category hazard      # Multi-hazard & site safety screening

# Generate executive HTML + JSON dossier from existing survey outputs:
python main.py --report

# Start the MCP server:
python -m src.mcp_server                     # Local stdio transport
python -m src.mcp_server --transport sse     # Cloud SSE transport (port 8000)
```

---

## 🏗️ Operational Intelligence Engines

| Category | Engine | Core Satellite Inputs | Primary Deliverables |
|:---|:---|:---|:---|
| **Cat 1: WATER** | [`src/engines/water.py`](src/engines/water.py) | ALOS PALSAR HV, Copernicus DEM 30m, ESA WorldCover, Sentinel-2, CHIRPS | `groundwater_potential_map.png`, `candidate_borehole_sites.csv/.geojson/.kmz`, `gwpz_index.tif` |
| **Cat 2: MINERALS** | [`src/engines/minerals.py`](src/engines/minerals.py) | Sentinel-2 GeoMAD (SWIR/NIR/Red/Blue), ALOS PALSAR, DEM | `mineral_prospectivity_map.png`, `candidate_mineral_targets.csv/.geojson/.kmz`, `mineral_prospectivity_index.tif` |
| **Cat 3: SOIL & LAND** | [`src/engines/soil.py`](src/engines/soil.py) | Sentinel-2 (NDVI, NDMI, BSI), Copernicus DEM, ESA WorldCover, CHIRPS | `soil_capability_map.png`, `candidate_land_zones.csv/.geojson/.kmz`, `soil_capability_index.tif` |
| **Cat 5: HAZARD & RISK** | [`src/engines/hazard.py`](src/engines/hazard.py) | Landsat WOfS 1984-2024 water frequency, DEM slope/ponding, Sentinel-2 dry biomass fuel | `hazard_risk_map.png`, `safest_buildable_sites.csv/.geojson/.kmz`, `hazard_composite_index.tif` |
| **EXECUTIVE DOSSIER** | [`src/report.py`](src/report.py) | Consolidated outputs from all categories | `SiteSurveyor_Intelligence_Report.html` (self-contained, base64 maps), `master_site_dossier.json` |

---

## 📂 Project Structure

```
SiteSurveyorAI/
├── main.py                     # Unified CLI runner
├── mcp_config.json             # Ready-to-use MCP configuration block
├── requirements.txt            # Python dependencies (includes mcp>=2.3.0)
├── README.md
├── docs/
│   ├── MCP_GUIDE.md            # Complete guide for connecting AI agents to the MCP server
│   └── PLATFORM_PLAN.md        # Comprehensive 10-category platform architecture
├── data/
│   ├── raw/                    # Cached DE Africa rasters (dem, alos, geomad, lc, wofs, chirps)
│   └── external/               # Geological context & mining deposits (USGS MRDS)
├── outputs/                    # Output GeoTIFFs, PNG maps, GeoJSON, CSV, KML/KMZ, and HTML reports
└── src/
    ├── __init__.py
    ├── config.py               # Central AOI, CRS (UTM 35S), 30m grid extents, and AHP weights
    ├── fetch_data.py           # WCS 2.1.0 satellite acquisition from DE Africa Sandbox
    ├── report.py               # Executive multi-category HTML + JSON dossier generator
    ├── mcp_server.py           # Direct MCP entrypoint runner
    ├── mcp/
    │   ├── __init__.py
    │   └── server.py           # Official MCP 2.x server definition with tools & resources
    ├── engines/
    │   ├── water.py            # Category 1: Groundwater potential & precision siting
    │   ├── minerals.py         # Category 2: Shear-zone gold prospectivity screening
    │   ├── soil.py             # Category 3: Land capability & erosion risk
    │   └── hazard.py           # Category 5: Multi-hazard & site safety screening
    └── utils/
        ├── raster.py           # Safe raster I/O, reprojection, and plotting helpers
        ├── terrain.py          # Priority-flood sink fill, vectorized D8 flow, slope, TWI
        ├── spectral.py         # NDVI, NDMI, NDWI, iron oxide, hydroxyl, ferrous, bare soil
        ├── lineaments.py       # Canny + Probabilistic Hough lineament extraction
        ├── classification.py   # Pure NumPy 1-D natural breaks (Jenks) & spatial peak picking
        └── export.py           # Mobile-ready KML & compressed KMZ export for smartphone GPS
```

---

## 📱 Mobile Smartphone GPS Deliverables

Every category exports interactive Google Earth `.kmz` files formatted for mobile field navigation:
- Open directly in **Google Earth Mobile** or **Maps.me** on iOS/Android.
- Displays target property alongside ranked candidate sites with distance, score, class, and field verification instructions.

---

## ⚖️ Screening-Level Disclaimer

SiteSurveyor AI is an automated Earth observation screening and decision-support tool. It computes probabilistic potential, prospectivity, and hazard zonation from orbital sensors. It is **not** a replacement for certified on-site engineering, hydrogeological (VES/ERT), geotechnical, or mining assay verifications. Ground truthing is required prior to drilling, excavation, or capital expenditure.

---

## 📜 License & Attribution

**Proprietary** — © Eineva Labs. Built for automated environmental and mineral intelligence.
