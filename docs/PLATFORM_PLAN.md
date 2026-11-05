# SiteSurveyor AI — Platform Capability Plan

**Project**: SiteSurveyor AI  
**Organization**: Eineva Labs  
**Date**: 2026-11-05  
**Status**: Planning Phase  

---

## Executive Summary

SiteSurveyor AI is a satellite-derived geospatial intelligence platform that transforms raw Earth observation data into actionable, site-specific **screening-level** decision reports. Capabilities are generated primarily from optical, radar/SAR, thermal, and elevation imagery, but high-confidence decisions require field validation such as geophysical surveys, soil sampling, drilling, or professional engineering assessment.

The platform accepts a single GPS coordinate and an Area of Interest (AOI) radius, then produces a comprehensive **Site Intelligence Report** scoring the location across up to 10 analysis domains.

---

## Satellite Data Sources

All processing draws from freely available or low-cost satellite archives:

| Source | Type | Resolution | Key Bands / Products |
|:---|:---|:---|:---|
| Sentinel-2 MSI | Optical (VNIR-SWIR) | 10–20 m | B2, B3, B4, B8, B8A, B11, B12 |
| Landsat 8/9 OLI + TIRS | Optical + Thermal | 30 m (100 m thermal) | VNIR, SWIR, LST |
| ALOS PALSAR / PALSAR-2 | L-Band SAR | 25 m | HH, HV polarizations |
| Sentinel-1 | C-Band SAR | 10 m | VV, VH polarizations |
| Copernicus DEM GLO-30 | Elevation | 30 m | Height above ellipsoid |
| ASTER | VNIR-SWIR-TIR | 15–90 m | 14 bands (mineralogy, thermal) |
| ESA WorldCover | Land Classification | 10 m | 11 land cover classes |
| CHIRPS | Rainfall | ~5 km | Monthly precipitation; regional context, not parcel-scale measurement |
| Landsat WOfS | Water Observations | 30 m | All-time water frequency |
| MODIS | Multispectral + Thermal | 250 m–1 km | Day/night LST, NDVI, albedo; regional-to-landscape context |
| VIIRS Nightlights | Nighttime Radiance | 500 m | Settlement and activity context |

**Primary API**: Digital Earth Africa (DE Africa) Sandbox WCS 2.1.0  
**Supplementary APIs**: NASA POWER, Google Earth Engine, USGS EarthExplorer

---

## The 10 Capability Categories

---

### 🔵 Category 1: WATER — Groundwater & Surface Water Intelligence

> *"Where do I drill? Will it last? How much will I get?"*

**Target Buyers**: Homeowners, farmers, NGOs, rural councils, drilling contractors

#### Capabilities

| # | Capability | Satellite Input | Processing Method |
|:--|:-----------|:----------------|:------------------|
| 1.1 | **Structural Fracture & Fault Mapping** | ALOS PALSAR (HV) + Copernicus DEM | Canny edge detection + Probabilistic Hough Transform on fused SAR backscatter and DEM hillshade; directional fracture density (km/km²) |
| 1.2 | **Topographic Wetness Index (TWI)** | Copernicus DEM | Sink filling → D8/D-infinity flow accumulation → TWI = ln(A / tan β) |
| 1.3 | **Drainage Density & Stream Network** | Copernicus DEM | Flow accumulation thresholding → Strahler ordering → kernel density (km/km²) |
| 1.4 | **Land Cover Infiltration Capacity** | ESA WorldCover 2021 | Reclassification of 11 land cover classes into infiltration capacity scores (0–1) |
| 1.5 | **Rainfall Recharge Estimation** | CHIRPS Monthly | Multi-year mean annual precipitation; wet/dry season ratio |
| 1.6 | **Vegetation Moisture Proxy (NDVI / NDMI)** | Sentinel-2 (B4, B8, B11) | NDVI = (NIR − Red) / (NIR + Red); NDMI = (NIR − SWIR1) / (NIR + SWIR1) |
| 1.7 | **Perennial vs. Seasonal Aquifer Differentiation** | Sentinel-2 / Landsat time-series | Multi-year dry-season (Oct/Nov) NDMI and NDWI analysis; phreatophyte detection via persistent green anomalies |
| 1.8 | **Weathering / Regolith Proxy Mapping** | DEM + ALOS PALSAR | Terrain curvature + surface roughness + radar backscatter indicators; requires geological or borehole validation and does not directly measure thickness |
| 1.9 | **Contamination Risk Buffering** | DEM + WorldCover | Slope-directed contamination flowpath modeling from pit latrines, kraals, cemeteries; automated 30 m+ exclusion buffers |
| 1.10 | **Small Dam & Weir Siting** | Copernicus DEM | Micro-catchment delineation → valley bottleneck detection → storage-to-wall volume ratio optimization |
| 1.11 | **Wetland & Spring Discharge Detection** | Landsat TIRS + Sentinel-2 | Dry-season thermal anomaly (cool spots) + persistent NDWI positive zones |
| 1.12 | **Apparent Thermal Inertia (ATI) Screening** | MODIS / Landsat TIRS | ATI = (1 − Albedo) / ΔT; highlights relative moisture and material contrasts, not direct groundwater depth or saturation |
| 1.13 | **Candidate Borehole Site Ranking** | All above layers | Weighted multi-criteria overlay (AHP) → natural breaks classification → local peak picking with spacing constraints |

#### Output Products
- `groundwater_potential_zones.tif` — Classified raster (Very Low → Very High)
- `gwpz_index.tif` — Continuous 0–100 index
- `candidate_borehole_sites.csv` / `.geojson` — Ranked GPS coordinates
- `groundwater_potential_map.png` — Cartographic map (220 dpi)
- `evidence_layers.png` — All input layers visualized
- `site_zoom_map.png` — 5×5 km detail around target
- `contamination_exclusion_zones.geojson` — No-drill buffer polygons

---

### 🟡 Category 2: MINERALS — Exploration & Prospectivity Targeting

> *"Where should I dig? Where are the reefs and shears?"*

**Target Buyers**: Junior miners, artisanal syndicates, exploration companies, claim holders

#### Capabilities

| # | Capability | Satellite Input | Processing Method |
|:--|:-----------|:----------------|:------------------|
| 2.1 | **Structural Lineament Density** | ALOS PALSAR (HV) + DEM hillshade | Canny + Hough on SAR/hillshade fusion; density in km/km² |
| 2.2 | **Lineament Intersection & Dilational Jog Detection** | Derived from 2.1 | Cross-cutting points with >20° angular disparity; kernel density of intersection nodes |
| 2.3 | **Iron Oxide / Gossan Detection** | Sentinel-2 (B2, B4, B11) | Gossan Index = (SWIR1/Red) × (Red/Blue); Band ratio B4/B2 |
| 2.4 | **Hydroxyl / Clay Alteration (Crosta PCA)** | Sentinel-2 (B2, B4, B11, B12) | PCA on 4-band subset; extract eigenvector with opposing SWIR1 vs SWIR2 loadings |
| 2.5 | **Ferrous / Mafic Mineral Index** | Sentinel-2 (B8, B11) | SWIR1/NIR ratio with NDVI residual correction |
| 2.6 | **Quartz & Silicification Index** | ASTER TIR (B10, B11, B12) | Silica Index = B11² / (B10 × B12); quartz vein outcrop detection |
| 2.7 | **Pegmatite and Alteration Screening** | Sentinel-2 SWIR / ASTER SWIR | B12/B11 and B8A/B11 ratios for alteration and lithologic contrasts; lithium presence requires field spectroscopy, sampling, and laboratory assays |
| 2.8 | **Ultramafic Prospectivity Screening** | Sentinel-2 + ASTER | Mg-OH and ferrous/hydroxyl contrasts used to prioritize targets; commodity presence and grade require geological mapping and assays |
| 2.9 | **Alluvial & Placer Gold Trap Mapping** | Copernicus DEM | Stream Power Index (SPI) = As × tan(β); Sediment Transport Index (STI); hydraulic drop zone detection |
| 2.10 | **Structural Strike Rose Diagram** | Derived from 2.1 | Azimuth computation of all lineament segments; binned orientation histogram |
| 2.11 | **Vegetation Residual Correction** | Sentinel-2 (B4, B8) | Polynomial regression of alteration indices against NDVI to remove false anomalies from green canopy |
| 2.12 | **Known Deposit Proximity (Endowment Context)** | USGS MRDS + curated databases | Distance-decay context from documented mines and occurrences; incomplete public records must be reported as a limitation |

#### Output Products
- `mineral_prospectivity_zones.tif` — Classified raster per commodity
- `mineral_prospectivity_index.tif` — Continuous 0–100 index
- `candidate_targets.csv` / `.geojson` — Ranked exploration targets
- `alteration_map.png` — Hydrothermal alteration composite
- `structural_map.png` — Lineaments, intersections, and rose diagram
- `evidence_layers.png` — All input layers

---

### 🟤 Category 3: SOIL & LAND — Agricultural Suitability Mapping

> *"Is this land worth buying? What can I grow on it?"*

**Target Buyers**: Agri-investors, commercial farmers, land buyers, tobacco/horticulture operations, diaspora purchasers

#### Capabilities

| # | Capability | Satellite Input | Processing Method |
|:--|:-----------|:----------------|:------------------|
| 3.1 | **Soil Moisture Capacity Index** | Sentinel-1 (VV/VH) + Sentinel-2 | SAR backscatter decomposition (moisture vs roughness) fused with optical NDMI |
| 3.2 | **Soil Organic Carbon Proxy** | Sentinel-2 (bare-soil pixels) | Bare Soil Index + spectral darkness in SWIR; correlation with organic matter content |
| 3.3 | **Erosion Susceptibility (RUSLE LS-Factor)** | Copernicus DEM | LS = (Flow Accumulation × Cell Size / 22.13)^0.4 × (sin(slope) / 0.0896)^1.3 |
| 3.4 | **Gully Hazard Mapping** | DEM + Sentinel-2 time-series | Stream Power Index thresholding + bare-soil expansion detection |
| 3.5 | **Irrigation Suitability Zonation** | DEM + CHIRPS + WorldCover | Slope classes (<2%, 2–5%, 5–8%, >8%) × water proximity × rainfall adequacy |
| 3.6 | **Crop Type Zonation** | CHIRPS + DEM + WorldCover | Rainfall regime + elevation + aspect + frost risk → suitability matrix per crop |
| 3.7 | **Frost Hollow & Cold Air Drainage** | Copernicus DEM | Topographic depression detection; cold air pooling modeling via inverted flow accumulation |
| 3.8 | **Waterlogging & Drainage Impediment** | DEM TWI + Sentinel-1 | Persistent high TWI zones + SAR wet-season backscatter anomalies |

#### Output Products
- `agricultural_suitability_zones.tif` — Classified raster
- `soil_quality_index.tif` — Continuous 0–100 composite
- `erosion_risk_map.png` — RUSLE LS-factor visualization
- `irrigation_zones.geojson` — Irrigable land polygons
- `crop_suitability_matrix.json` — Per-crop scoring

---

### 🟢 Category 4: VEGETATION & BIOMASS — Rangeland, Forestry & Carbon

> *"How productive is this land? Is it degrading?"*

**Target Buyers**: Ranchers, conservancies, forestry operations, carbon credit developers, insurance underwriters

#### Capabilities

| # | Capability | Satellite Input | Processing Method |
|:--|:-----------|:----------------|:------------------|
| 4.1 | **Vegetation Productivity Trend (5–10 yr)** | Sentinel-2 / Landsat NDVI archive | Linear regression of annual peak-season NDVI; Mann-Kendall trend significance |
| 4.2 | **Carrying Capacity Estimation** | Sentinel-2 NDVI + CHIRPS | Biomass proxy (kg DM/ha) from NDVI × rainfall interaction; stocking rate calculation |
| 4.3 | **Bush Encroachment Detection** | Sentinel-2 + Sentinel-1 | Woody cover fraction change via SAR texture + optical NDVI seasonality separation (woody vs grass) |
| 4.4 | **Canopy Density & Timber Volume** | Sentinel-1 + Sentinel-2 | SAR backscatter (HV correlates with above-ground biomass) + canopy height proxy |
| 4.5 | **Carbon Stock Estimation (AGB)** | ALOS PALSAR (HV) + Sentinel-2 | Allometric AGB models calibrated to L-band backscatter; tCO₂/ha output |
| 4.6 | **Fire Scar History & Burn Frequency** | Sentinel-2 / Landsat NBR | Normalized Burn Ratio time-series; fire return interval mapping |
| 4.7 | **Land Degradation Neutrality (LDN) Index** | Multi-source composite | UNCCD SDG 15.3.1 framework: productivity + land cover change + soil organic carbon |

#### Output Products
- `vegetation_health_trend.tif` — NDVI trend slope
- `biomass_map.tif` — Above-ground biomass (tDM/ha)
- `carbon_stock_map.tif` — Carbon density (tCO₂/ha)
- `fire_frequency_map.png` — Burn count per pixel
- `degradation_index.tif` — LDN composite

---

### 🔴 Category 5: HAZARD & RISK — Natural Disaster & Environmental Risk

> *"Is this site safe to build on? What could go wrong?"*

**Target Buyers**: Insurance companies, banks (collateral assessment), municipal planners, real estate developers, construction firms

#### Capabilities

| # | Capability | Satellite Input | Processing Method |
|:--|:-----------|:----------------|:------------------|
| 5.1 | **Flood Inundation Modeling** | DEM + Landsat WOfS | Flow accumulation → flood-prone flat zones + historical water extent overlay |
| 5.2 | **Landslide Susceptibility** | DEM + CHIRPS + WorldCover | Slope + curvature + lithology proxy + rainfall intensity; logistic regression or weighted overlay |
| 5.3 | **Soil Liquefaction & Collapsible Soil Risk** | DEM + Sentinel-1 | Alluvial flat detection + SAR moisture anomaly in sandy deposits |
| 5.4 | **Wildfire Spread Corridor Modeling** | DEM + WorldCover + NDVI | Fuel load (NDVI biomass) × slope × aspect (wind channeling) |
| 5.5 | **Drought Severity & Frequency Index** | CHIRPS (20+ years) | Standardized Precipitation Index (SPI) at 3, 6, 12-month scales; return period analysis |
| 5.6 | **Sinkhole / Doline Risk (Karst Terrain)** | Copernicus DEM | Circular depression detection via topographic depression filling; curvature anomalies |
| 5.7 | **Seismic Proximity Scoring** | USGS earthquake catalog | Distance to historical epicenters + active fault proximity |

#### Output Products
- `hazard_composite_index.tif` — Combined risk score (0–100, low = safe)
- `flood_risk_zones.geojson` — Inundation polygons
- `landslide_susceptibility_map.png` — Classified slope failure risk
- `drought_frequency.tif` — Return period raster
- `hazard_report.json` — Per-hazard scoring

---

### ⚪ Category 6: INFRASTRUCTURE & CONSTRUCTION — Site Due Diligence

> *"Can I build here? What will it cost?"*

**Target Buyers**: Construction companies, solar/wind developers, telecoms tower planners, road engineers

#### Capabilities

| # | Capability | Satellite Input | Processing Method |
|:--|:-----------|:----------------|:------------------|
| 6.1 | **Foundation Suitability Classification** | Sentinel-1 + Sentinel-2 + DEM | SAR roughness (rock vs soil) + spectral classification (clay vs sand vs laterite) |
| 6.2 | **Cut-and-Fill Volume Estimation** | Copernicus DEM | Target platform elevation → volume above/below existing surface per cell |
| 6.3 | **Access Road Gradient Analysis** | Copernicus DEM | Least-cost path from nearest road to target; maximum gradient along path |
| 6.4 | **Infrastructure Proximity Scoring** | WorldCover + OpenStreetMap | Distance to nearest road, power line, settlement, water source |
| 6.5 | **Borrow Pit / Aggregate Source Detection** | Sentinel-2 + DEM | Exposed rock/gravel outcrop identification via bare-soil spectral indices + roughness |
| 6.6 | **Solar Farm Terrain Suitability** | Copernicus DEM + WorldCover | Flat (<5°) + south/north-facing (hemisphere-dependent) + non-agricultural + low-shadow zones |
| 6.7 | **Telecoms Tower Line-of-Sight Analysis** | Copernicus DEM | Viewshed computation from candidate tower locations; coverage radius mapping |

#### Output Products
- `construction_suitability_zones.tif` — Classified raster
- `access_route.geojson` — Optimal access path with gradient profile
- `cut_fill_volume.json` — Earthworks volume estimate
- `viewshed_coverage.tif` — Line-of-sight binary raster

---

### 🟣 Category 7: PROPERTY & REAL ESTATE — Land Valuation Intelligence

> *"What is this plot actually worth?"*

**Target Buyers**: Diaspora buyers purchasing remotely, real estate agents, banks valuing collateral, estate liquidators

#### Capabilities

| # | Capability | Satellite Input | Processing Method |
|:--|:-----------|:----------------|:------------------|
| 7.1 | **Composite Land Quality Score** | All categories combined | Weighted combination of water, soil, minerals, hazard, access, energy scores → single 0–100 index |
| 7.2 | **Change Detection (Before/After)** | Sentinel-2 time-series | Bi-temporal NDVI / NDBI differencing; has the land been stripped, mined, deforested, or built on? |
| 7.3 | **Boundary Encroachment Detection** | Sentinel-2 + WorldCover | Unauthorized clearing or building expansion across cadastral boundaries |
| 7.4 | **Neighborhood Development Trajectory** | WorldCover + VIIRS Nightlights | 5-year trend of built-up area expansion + nighttime light intensity growth |
| 7.5 | **Viewshed & Scenic Value Analysis** | Copernicus DEM | 360° viewshed from property center; visible area, horizon distance, scenic mountain/water features |
| 7.6 | **Legal Land Use Conflict Screening** | WorldCover + wetland/forest masks | Flags if property overlaps protected wetlands, riparian buffers, or gazetted forest reserves |

#### Output Products
- `land_quality_score.json` — Composite 0–100 rating with breakdown
- `change_detection_map.png` — Before/after comparison
- `development_trajectory.png` — 5-year growth trend visualization
- `viewshed_map.png` — Visible area from property
- `property_intelligence_report.pdf` — Branded client document

---

### 🟠 Category 8: ENERGY — Renewable Energy & Electrification Siting

> *"Where should I put solar panels, a wind turbine, or a mini-grid?"*

**Target Buyers**: Solar companies, rural electrification agencies, NGOs, off-grid homesteaders

#### Capabilities

| # | Capability | Satellite Input | Processing Method |
|:--|:-----------|:----------------|:------------------|
| 8.1 | **Solar Irradiance & Aspect Mapping** | Copernicus DEM + NASA POWER | Slope + aspect → annual insolation (kWh/m²/day); shadow casting from surrounding terrain |
| 8.2 | **Wind Exposure Corridor Detection** | Copernicus DEM | Ridgeline detection + valley channeling + Topographic Position Index for wind acceleration zones |
| 8.3 | **Mini-Hydro Head & Flow Estimation** | Copernicus DEM + CHIRPS | Stream gradient × catchment area × mean annual runoff → estimated power (kW) |
| 8.4 | **Off-Grid Community Clustering** | WorldCover + VIIRS Nightlights | Settlement detection + population density proxy → mini-grid sizing and optimal placement |
| 8.5 | **Solar Pump Sizing Engine** | DEM + NASA POWER | Irradiance × total dynamic head (elevation lift from borehole to tank) → pump wattage + panel count |
| 8.6 | **Transmission Line Corridor Optimization** | DEM + WorldCover | Least-cost path avoiding steep slopes, forests, wetlands, and settlements |

#### Output Products
- `solar_potential_map.tif` — Annual insolation raster
- `wind_exposure_zones.geojson` — High-wind corridor polygons
- `minihydro_candidates.csv` — Ranked sites with estimated kW
- `solar_pump_spec.json` — Pump size, panel count, daily yield
- `grid_corridor.geojson` — Optimal transmission route

---

### 🔵 Category 9: WILDLIFE & CONSERVATION — Habitat & Corridor Mapping

> *"Where are the animals moving? What habitat is left?"*

**Target Buyers**: National parks, conservancies, safari operators, international conservation NGOs, CAMPFIRE programs

#### Capabilities

| # | Capability | Satellite Input | Processing Method |
|:--|:-----------|:----------------|:------------------|
| 9.1 | **Habitat Suitability Modeling** | WorldCover + DEM + WOfS | Land cover type + water proximity + terrain ruggedness + human disturbance distance → species-specific HSI |
| 9.2 | **Wildlife Corridor Connectivity** | DEM + WorldCover | Least-cost path / circuit theory (Circuitscape logic) between protected areas through natural cover |
| 9.3 | **Poaching Pressure Proxy** | WorldCover + DEM | Road density + settlement proximity + forest cover loss rate → vulnerability index |
| 9.4 | **Wetland Health & Extent Change** | Landsat WOfS + Sentinel-2 | Multi-decadal water extent change; seasonal vs permanent wetland classification |
| 9.5 | **Human-Wildlife Conflict Zone Mapping** | WorldCover time-series | Agriculture/settlement expansion rate into wildlife buffer zones; conflict frontier delineation |
| 9.6 | **Biodiversity Proxy Index** | Sentinel-2 NDVI variability | Coefficient of variation of NDVI as habitat heterogeneity proxy |

#### Output Products
- `habitat_suitability_index.tif` — Species-specific HSI raster
- `wildlife_corridors.geojson` — Least-cost path polygons
- `conflict_zones.geojson` — Encroachment frontier polygons
- `wetland_change_map.png` — Multi-temporal extent comparison
- `conservation_report.json` — Summary metrics

---

### ⚫ Category 10: URBAN & SETTLEMENT — Planning & Growth Intelligence

> *"Where is the city growing? Where should services go?"*

**Target Buyers**: Municipal councils, urban planners, utility companies, telecoms, humanitarian organizations

#### Capabilities

| # | Capability | Satellite Input | Processing Method |
|:--|:-----------|:----------------|:------------------|
| 10.1 | **Informal Settlement Detection & Growth Tracking** | WorldCover + Sentinel-2 time-series | Built-up area classification + temporal expansion rate mapping |
| 10.2 | **Service Coverage Gap Analysis** | WorldCover + DEM + OSM | Distance from each settlement cluster to nearest borehole, clinic, school, paved road |
| 10.3 | **Impervious Surface & Stormwater Runoff** | Sentinel-2 NDBI + DEM | Normalized Difference Built-up Index + flow accumulation → urban flood ponding zones |
| 10.4 | **Urban Heat Island Mapping** | Landsat TIRS | Land Surface Temperature anomaly: built-up areas vs surrounding vegetation/water |
| 10.5 | **Illegal Land Clearing / Unauthorized Development** | Sentinel-2 bi-temporal change | NDVI loss + bare soil gain detection between two dates |
| 10.6 | **Population Density Estimation** | VIIRS Nightlights + WorldCover | Nighttime radiance × built-up fraction calibrated to census data |

#### Output Products
- `settlement_growth_map.tif` — Multi-temporal built-up expansion
- `service_gap_map.png` — Distance-to-service heatmap
- `urban_flood_risk.geojson` — Ponding zone polygons
- `heat_island_map.png` — LST anomaly visualization
- `urban_intelligence_report.json` — Summary metrics

---

## Composite Site Intelligence Report

The ultimate product is a **single-coordinate, multi-domain report** that layers all categories:

```
┌─────────────────────────────────────────────────────┐
│           SITE INTELLIGENCE REPORT                  │
│  Location: 19.5049°S, 29.8460°E                    │
│  AOI Radius: 12.5 km                               │
├─────────────────────────────────────────────────────┤
│                                                     │
│  💧  Water Potential          72 / 100   HIGH        │
│  ⛏️  Mineral Prospectivity    34 / 100   LOW         │
│  🌾  Agricultural Suitability 81 / 100   VERY HIGH   │
│  🌿  Vegetation / Biomass     65 / 100   MODERATE    │
│  🔥  Hazard Risk              12 / 100   LOW (SAFE) │
│  🏗️  Construction Feasibility 67 / 100   MODERATE   │
│  🏘️  Property Value Trend     ↑ GROWING             │
│  ☀️  Solar Energy Potential    88 / 100   VERY HIGH  │
│  🦁  Conservation Value       45 / 100   MODERATE    │
│  🏙️  Urban Service Coverage   73 / 100   HIGH       │
│                                                     │
│  OVERALL SITE RATING:  68 / 100                     │
│  DATA CONFIDENCE:      MODERATE                    │
│                                                     │
├─────────────────────────────────────────────────────┤
│  Top 3 Borehole Candidates (GPS)                    │
│  Top 3 Mineral Targets (GPS)                        │
│  Hazard Warnings & Exclusion Zones                  │
│  Recommended Next Steps                             │
└─────────────────────────────────────────────────────┘
```

Every domain score must include a confidence rating, data acquisition date, spatial resolution, dominant evidence layers, and a short explanation of uncertainty. Composite scores are prioritization aids, not guarantees of water yield, mineral grade, crop yield, property value, or engineering suitability.

## Validation and Uncertainty

The platform must distinguish between **observed measurements**, **derived indicators**, and **screening recommendations**. Reports should:

- Record source dataset versions, acquisition dates, cloud or quality masks, projections, resampling methods, and model parameters.
- Report confidence separately from the opportunity or risk score.
- Flag coarse inputs such as CHIRPS, MODIS, and VIIRS when they materially influence a site result.
- Include a field-verification checklist appropriate to the domain: geophysics and drilling for groundwater, mapping and assays for minerals, soil sampling for agriculture, and professional surveys for construction.
- Track validation outcomes from boreholes, assays, soil tests, hazard observations, and client feedback for later calibration.
- Never infer absence of a resource from missing public records or a low satellite score.

Initial validation datasets should be assembled before public launch. At minimum, the water and minerals products need representative known sites, documented outcomes, and acceptance thresholds for ranking accuracy and false-positive rates.

## Minimum Viable Product

The first release should focus on a single-coordinate report containing:

1. Water-potential screening using DEM, Sentinel-1/2, WorldCover, and rainfall context.
2. Mineral-prospectivity screening using structural and alteration indicators, without claiming commodity grade or deposit confirmation.
3. Basic flood, slope, and land-cover exclusions.
4. Ranked priority zones with evidence layers, confidence, data freshness, and field-verification guidance.
5. GeoJSON, GeoTIFF, PNG, JSON metadata, and a concise PDF report.

The remaining domains should be added only after the MVP has measurable validation results and a documented uncertainty model.

---

## Platform Architecture

```
                    User Input (GPS + AOI radius)
                              │
                              ▼
                 ┌────────────────────────┐
                 │   Data Acquisition     │
                 │   Engine               │
                 │   (DE Africa WCS +     │
                 │    NASA POWER +        │
                 │    USGS / OSM)         │
                 └───────────┬────────────┘
                             │
              Unified 30m UTM Grid (GeoTIFF stack)
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
   ┌────────────┐    ┌────────────┐    ┌────────────┐
   │  Category  │    │  Category  │    │  Category  │
   │  Engines   │    │  Engines   │    │  Engines   │
   │  (1–5)     │    │  (6–8)     │    │  (9–10)    │
   │            │    │            │    │            │
   │ Water      │    │ Infra      │    │ Wildlife   │
   │ Minerals   │    │ Property   │    │ Urban      │
   │ Soil       │    │ Energy     │    │            │
   │ Vegetation │    │            │    │            │
   │ Hazard     │    │            │    │            │
   └─────┬──────┘    └─────┬──────┘    └─────┬──────┘
         │                 │                 │
         └─────────────────┼─────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │   Report Compositor    │
              │   & Export Engine      │
              │                        │
              │   • GeoTIFF rasters    │
              │   • GeoJSON vectors    │
              │   • PNG cartography    │
              │   • KMZ mobile maps    │
              │   • PDF client reports │
              │   • JSON metadata      │
              └────────────────────────┘
```

---

## Implementation Priority

| Phase | Categories | Rationale |
|:------|:-----------|:----------|
| **Phase 1** | 🔵 Water + 🟡 Minerals | Core revenue generators; highest client demand in Zimbabwe |
| **Phase 2** | 🟤 Soil/Land + 🔴 Hazard/Risk | Expands to agriculture and insurance/banking markets |
| **Phase 3** | 🟠 Energy + ⚪ Infrastructure | Renewable energy and construction due diligence |
| **Phase 4** | 🟢 Vegetation + 🟣 Property | Carbon credits, rangeland, diaspora land buyers |
| **Phase 5** | 🔵 Wildlife + ⚫ Urban | Conservation NGOs and municipal planning contracts |

---

## Key Technical Notes

> [!IMPORTANT]
> All capabilities are **screening-level tools** derived from satellite imagery and other remotely sensed datasets at resolutions ranging from 10 m to approximately 5 km. They do not replace field verification (geophysical surveys, soil sampling, drilling, laboratory assays, or professional engineering assessments). All reports must carry appropriate disclaimers and confidence indicators.

> [!NOTE]
> The platform uses **expert-weighted multi-criteria decision analysis (AHP)** by default. AHP weights must be versioned and sensitivity-tested. When sufficient, representative ground-truth data becomes available (e.g., borehole yield records, assay results), the system can transition to supervised machine learning (Random Forest, XGBoost) for calibrated predictions, with held-out validation and uncertainty estimates.

---

*SiteSurveyor AI — Eineva Labs — Satellite Intelligence for Ground Decisions*
