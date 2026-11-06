"""
SiteSurveyor AI — Central Configuration & Dynamic AOI Context
=============================================================
All site parameters, dynamic AOI definitions, automatic UTM zone CRS projection,
grid extents, and AHP model weights are managed here.
"""
from __future__ import annotations

import os
from pathlib import Path

# Configure PROJ data paths before importing rasterio/pyproj
import pyproj.datadir
proj_dir = pyproj.datadir.get_data_dir()
os.environ["PROJ_DATA"] = proj_dir
os.environ["PROJ_LIB"] = proj_dir

import numpy as np
from dotenv import load_dotenv
from pyproj import Transformer
from rasterio.crs import CRS
from rasterio.transform import from_origin

load_dotenv()

# --- Paths ---
ROOT = Path(__file__).resolve().parents[1]

# Render's container filesystem is ephemeral: anything written under /app is discarded on
# every deploy and restart, which took the deliverable maps, the KMZ files and the
# executive report with it. SITESURVEYOR_STATE_DIR points the survey cache and the
# published outputs at a mounted disk instead. Unset, it is the repository root, so local
# runs and the test suite keep working exactly as before.
_state_override = os.getenv("SITESURVEYOR_STATE_DIR", "").strip()
STATE_DIR = Path(_state_override).expanduser() if _state_override else ROOT
DATA_DIR = STATE_DIR / "data"
RAW_BASE = DATA_DIR / "raw"
EXTERNAL = DATA_DIR / "external"
OUT = STATE_DIR / "outputs"
for d in (RAW_BASE, EXTERNAL, OUT):
    d.mkdir(parents=True, exist_ok=True)

# --- API ---
WCS_URL = "https://ows.digitalearth.africa/wcs"
API_KEY = (
    os.getenv("DEAFRICA_SANDBOX_API_KEY")
    or os.getenv("DE_AFRICA_TOKEN")
    or os.getenv("DE_AFRICA_API_KEY")
    or ""
)

HEADERS = {
    "User-Agent": "SiteSurveyorAI/2.0",
}
if API_KEY:
    HEADERS["Authorization"] = f"Bearer {API_KEY}"
    HEADERS["x-api-key"] = API_KEY

# --- Branding & Grid Base Constants ---
ANALYST = "Eineva Labs"
BRAND_COLOR = "#D14141"
CELL = 30.0  # metres

# Limit GDAL block cache to prevent greedy RAM consumption on constrained containers (512MB RAM)
os.environ.setdefault("GDAL_CACHEMAX", "32")
# Instruct glibc to promptly return freed heap pages back to the Linux OS kernel
os.environ.setdefault("MALLOC_TRIM_THRESHOLD_", "65536")

# Map render buffers scale with the square of this: a survey peaks at >500 MB of
# process memory with maps at 120 dpi, tripping the 512 MB Linux cgroup limit on Starter tier.
# At 90 dpi on-screen clarity is pristine while memory footprint drops by >44%.
MAP_DPI = int(os.getenv("MAP_DPI", "90"))

# --- Water Model Weights (AHP) ---
WATER_WEIGHTS = {
    "lineament_density": 0.26,
    "slope": 0.18,
    "twi": 0.18,
    "landcover_infiltration": 0.12,
    "drainage_density": 0.10,
    "rainfall": 0.08,
    "ndvi": 0.08,
}

# --- Mineral Model Weights (AHP) ---
MINERAL_WEIGHTS = {
    "lineament_density": 0.28,
    "lineament_intersections": 0.18,
    "iron_oxide": 0.14,
    "hydroxyl_clay": 0.14,
    "ferrous_mafic": 0.12,
    "relative_relief": 0.08,
    "endowment": 0.06,
}

# --- Soil & Land Model Weights (AHP) ---
SOIL_WEIGHTS = {
    "erosion_risk":   0.25,
    "soil_moisture":  0.20,
    "vegetation":     0.18,
    "landcover":      0.15,
    "wetness":        0.12,
    "rainfall":       0.10,
}

# --- Hazard & Environmental Risk Weights (AHP) ---
HAZARD_WEIGHTS = {
    "flood_inundation": 0.30,
    "slope_failure":    0.20,
    "erosion_washout":  0.20,
    "wildfire_fuel":    0.15,
    "drought_stress":   0.15,
}

# --- Selectable Input Sources ---
# Only layers whose alternative Digital Earth Africa coverages are interchangeable at the
# engine level: one band, same units, same class scheme. GeoMAD is deliberately absent -
# gm_s2_annual carries 14 bands and gm_ls8_annual / gm_ls8_ls9_annual carry 10, while the
# engines read bands by position (1, 3, 7, 9, 10), so switching it would feed smad, bcmad
# and count into the vegetation maths and still return a confident-looking 0-100 score.
DATA_SOURCES: dict[str, dict] = {
    "dem": {
        "label": "Elevation model",
        "layer": "dem",
        "default": "dem_cop_30",
        "options": {
            "dem_cop_30": "Copernicus DEM 30 m",
            "dem_srtm": "SRTM 30 m",
            "nasadem": "NASA DEM 30 m",
        },
    },
    "landcover": {
        "label": "Land cover map",
        "layer": "landcover",
        "default": "esa_worldcover_2021",
        "options": {
            "esa_worldcover_2021": "ESA WorldCover 2021",
            "esa_worldcover_2020": "ESA WorldCover 2020",
        },
    },
}

ACTIVE_SOURCES: dict[str, str] = {k: v["default"] for k, v in DATA_SOURCES.items()}

# The inputs a caller cannot choose: one coverage each, pinned in fetch_data.fetch_all.
# Listed so the API, the sandbox and every report can name what produced a score instead of
# leaving it implied -- a reader who knows the vegetation maths runs on a 2023 Sentinel-2
# composite can judge the number; one who does not, cannot.
FIXED_SOURCES: dict[str, str] = {
    "alos": "ALOS PALSAR 2007 L-band mosaic",
    "wofs": "Water Observations from Space, Landsat all-time summary",
    "geomad": "Sentinel-2 Annual GeoMAD, 2023 composite",
    "rainfall": "CHIRPS monthly rainfall, 24-month mean",
    "crop_mask": "Digital Earth Africa cropland extent",
    "fc_ls": "Digital Earth Africa Landsat fractional-cover annual summary",
}

# --- Dynamic AOI State Variables ---
TARGET_LON: float = 29.84597927542165
TARGET_LAT: float = -19.50487490194389
HALF_DEG: float = 0.12
UTM_ZONE: int = 35
EPSG: int = 32735
BBOX_WGS84: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
LOCAL_CRS: CRS = None
TO_LOCAL: Transformer = None
TO_WGS: Transformer = None
TO_6933: Transformer = None
XMIN: float = 0.0
XMAX: float = 0.0
YMIN: float = 0.0
YMAX: float = 0.0
WIDTH: int = 0
HEIGHT: int = 0
TRANSFORM = None
TARGET_X: float = 0.0
TARGET_Y: float = 0.0
TARGET_COL: int = 0
TARGET_ROW: int = 0
# Neutral defaults on purpose: a real person's name and street address used to be baked
# into these and published on the public dossier of every instance, including installs
# that never ran a survey of that property.
DEFAULT_CLIENT: str = "Site Survey"
DEFAULT_CLIENT_ADDRESS: str = "Property location not specified"
CLIENT: str = DEFAULT_CLIENT
CLIENT_ADDRESS: str = DEFAULT_CLIENT_ADDRESS
RAW: Path = RAW_BASE
AOI_SLUG: str = ""


def set_target_site(
    lat: float = -19.50487490194389,
    lon: float = 29.84597927542165,
    half_deg: float = 0.12,
    client: str | None = None,
    address: str | None = None,
) -> None:
    """
    Dynamically configure active target coordinates, UTM zone projection, and 30m grid extents.

    Args:
        lat: Target latitude in decimal degrees.
        lon: Target longitude in decimal degrees.
        half_deg: Half-size of bounding box in degrees (default 0.12, ~13 km).
        client: Client or project name.
        address: Client property address or description.
    """
    global TARGET_LAT, TARGET_LON, HALF_DEG, BBOX_WGS84
    global UTM_ZONE, EPSG
    global LOCAL_CRS, TO_LOCAL, TO_WGS, TO_6933
    global XMIN, XMAX, YMIN, YMAX, WIDTH, HEIGHT, TRANSFORM
    global TARGET_X, TARGET_Y, TARGET_COL, TARGET_ROW
    global CLIENT, CLIENT_ADDRESS, RAW, AOI_SLUG

    TARGET_LAT = float(lat)
    TARGET_LON = float(lon)
    HALF_DEG = float(half_deg)

    if client:
        CLIENT = client
    if address:
        CLIENT_ADDRESS = address

    # Automatic UTM Zone calculation:
    # 6-degree longitudinal zones, 326xx for North, 327xx for South
    zone_number = int(np.floor((TARGET_LON + 180.0) / 6.0)) + 1
    epsg_code = (32700 + zone_number) if TARGET_LAT < 0 else (32600 + zone_number)
    UTM_ZONE = zone_number
    EPSG = epsg_code

    LOCAL_CRS = CRS.from_epsg(epsg_code)
    TO_LOCAL = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg_code}", always_xy=True)
    TO_WGS = Transformer.from_crs(f"EPSG:{epsg_code}", "EPSG:4326", always_xy=True)
    TO_6933 = Transformer.from_crs("EPSG:4326", "EPSG:6933", always_xy=True)

    BBOX_WGS84 = (
        TARGET_LON - HALF_DEG,
        TARGET_LAT - HALF_DEG,
        TARGET_LON + HALF_DEG,
        TARGET_LAT + HALF_DEG,
    )

    # Transform 4 bbox corners to metric coordinates
    _lon = [BBOX_WGS84[0], BBOX_WGS84[2], BBOX_WGS84[2], BBOX_WGS84[0]]
    _lat = [BBOX_WGS84[1], BBOX_WGS84[1], BBOX_WGS84[3], BBOX_WGS84[3]]
    _x, _y = TO_LOCAL.transform(_lon, _lat)

    XMIN = float(np.floor(min(_x) / CELL) * CELL)
    XMAX = float(np.ceil(max(_x) / CELL) * CELL)
    YMIN = float(np.floor(min(_y) / CELL) * CELL)
    YMAX = float(np.ceil(max(_y) / CELL) * CELL)

    WIDTH = int(round((XMAX - XMIN) / CELL))
    HEIGHT = int(round((YMAX - YMIN) / CELL))
    TRANSFORM = from_origin(XMIN, YMAX, CELL, CELL)

    TARGET_X, TARGET_Y = TO_LOCAL.transform(TARGET_LON, TARGET_LAT)
    TARGET_COL = int((TARGET_X - XMIN) / CELL)
    TARGET_ROW = int((YMAX - TARGET_Y) / CELL)

    # AOI-specific directory for satellite caching
    lat_h = 'S' if TARGET_LAT < 0 else 'N'
    lon_h = 'E' if TARGET_LON >= 0 else 'W'
    AOI_SLUG = f"{abs(TARGET_LAT):.2f}{lat_h}_{abs(TARGET_LON):.2f}{lon_h}"
    RAW = RAW_BASE / AOI_SLUG
    RAW.mkdir(parents=True, exist_ok=True)


def clear_target_site() -> None:
    """Return the live AOI and client identity to the neutral defaults.

    ``set_target_site`` only overwrites CLIENT when handed a truthy name, so a finished
    survey's client sticks to the module until something replaces it. Wiping the processed
    data has to replace it, or the next report would stamp this client's name on an
    instance that now holds no data about them at all.
    """
    set_target_site(client=DEFAULT_CLIENT, address=DEFAULT_CLIENT_ADDRESS)


def check_data_sources(sources: dict[str, str] | None) -> dict[str, str]:
    """Validate a selection against DATA_SOURCES and return the complete choice set.

    Rejects anything outside the registry rather than passing a bad coverageid through to
    WCS, where it would surface as a download failure several layers away from the choice
    that caused it. Layers the caller leaves out come back as their defaults rather than as
    whatever the previous survey selected: a request should describe the run it produces in
    full, or a report would state a source nobody asked for.
    """
    chosen = {key: spec["default"] for key, spec in DATA_SOURCES.items()}
    for key, value in (sources or {}).items():
        spec = DATA_SOURCES.get(key)
        if spec is None:
            raise ValueError(
                f"unknown data source '{key}'; selectable layers are "
                f"{', '.join(sorted(DATA_SOURCES))}"
            )
        if value not in spec["options"]:
            raise ValueError(
                f"'{value}' is not an available {spec['label'].lower()}; choose one of "
                f"{', '.join(spec['options'])}"
            )
        chosen[key] = value
    return chosen


def set_data_sources(sources: dict[str, str] | None) -> dict[str, str]:
    """Point the selectable input layers at the requested DEA coverages."""
    chosen = check_data_sources(sources)
    ACTIVE_SOURCES.update(chosen)
    return chosen


def clear_data_sources() -> None:
    """Restore every selectable layer to the coverage the model is calibrated on."""
    ACTIVE_SOURCES.update({k: v["default"] for k, v in DATA_SOURCES.items()})


def source_labels(sources: dict[str, str] | None = None) -> dict[str, str]:
    """Coverage id -> registry display name, for the places that quote a source to a person."""
    chosen = ACTIVE_SOURCES if sources is None else sources
    return {
        key: DATA_SOURCES[key]["options"][value]
        for key, value in chosen.items()
        if DATA_SOURCES.get(key) and value in DATA_SOURCES[key]["options"]
    }


# Initialize default AOI on import (Gweru, Zimbabwe)
set_target_site()
