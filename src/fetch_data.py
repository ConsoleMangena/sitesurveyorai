"""
SiteSurveyor AI — Data Acquisition Engine
==========================================
Fetch satellite Earth observation layers from Digital Earth Africa's
open OGC Web Coverage Service (WCS 2.1.0) using personal access token authentication.
Supports dynamic bounding box and target coordinate context.
"""
from __future__ import annotations

import os
import sys
import time as _time
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Import config FIRST to ensure PROJ_LIB and PROJ_DATA are configured before rasterio
import src.config as cfg

import numpy as np
import rasterio
import requests
from pyproj import Transformer


def _xy_bbox(bbox: tuple[float, float, float, float], target_crs: str = "EPSG:6933") -> tuple[float, float, float, float]:
    """Convert WGS84 bbox (minx, miny, maxx, maxy) to target CRS."""
    if target_crs == "EPSG:6933":
        transformer = cfg.TO_6933
    elif target_crs == str(cfg.LOCAL_CRS) or target_crs == f"EPSG:{cfg.LOCAL_CRS.to_epsg() if cfg.LOCAL_CRS else 32735}":
        transformer = cfg.TO_LOCAL
    else:
        transformer = Transformer.from_crs("EPSG:4326", target_crs, always_xy=True)

    xs, ys = transformer.transform(
        [bbox[0], bbox[2], bbox[2], bbox[0]],
        [bbox[1], bbox[1], bbox[3], bbox[3]],
    )
    return min(xs), min(ys), max(xs), max(ys)


def _url(coverage: str, bbox: tuple[float, float, float, float], stamp: str | None = None,
         projected: bool = False, target_crs: str = "EPSG:6933") -> str:
    """Build WCS GetCoverage request URL."""
    params = [
        "service=WCS",
        "version=2.1.0",
        "request=GetCoverage",
        f"coverageid={coverage}",
    ]
    if projected:
        x0, y0, x1, y1 = _xy_bbox(bbox, target_crs)
        params += [f"subset=x({x0:.0f},{x1:.0f})", f"subset=y({y0:.0f},{y1:.0f})"]
    else:
        params += [
            f"subset=Lat({bbox[1]:.6f},{bbox[3]:.6f})",
            f"subset=Long({bbox[0]:.6f},{bbox[2]:.6f})",
        ]
    if stamp:
        params.append(f'subset=time(%22{stamp}%22)')
    params.append("format=image/geotiff")
    return f"{cfg.WCS_URL}?{'&'.join(params)}"


def _download(url: str, out: Path, retries: int = 4, optional: bool = False) -> bool:
    """Download raster with retry logic and GeoTIFF header validation."""
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers=cfg.HEADERS, timeout=300)
            if r.status_code == 200 and len(r.content) > 4 and r.content[:2] in (b"II", b"MM"):
                out.write_bytes(r.content)
                with rasterio.open(out) as ds:
                    print(f"[ok] {out.stem:12s} {ds.count:2d} band(s)  {ds.width}x{ds.height}  {ds.crs}")
                return True
            if optional and r.status_code in (404, 400):
                print(f"[skip] {out.stem}: no data in archive ({r.status_code})")
                return False
            print(f"[retry {attempt}] {out.stem}: HTTP {r.status_code} {r.text[:120]}")
        except Exception as exc:
            print(f"[retry {attempt}] {out.stem}: {exc}")
        _time.sleep(2 * attempt)
    if optional:
        print(f"[skip] {out.stem}: unavailable after {retries} retries")
        return False
    raise RuntimeError(f"Could not download {out.stem} from {url}")


def fetch(name: str, coverage: str, stamp: str | None = None, projected: bool = False,
          target_crs: str = "EPSG:6933", retries: int = 4, optional: bool = False,
          cache: bool = True) -> Path | None:
    """
    Fetch a DE Africa layer via WCS with local caching in the active AOI directory.
    """
    out = cfg.RAW / f"{name}.tif"

    if cache and out.exists() and out.stat().st_size > 0:
        try:
            with rasterio.open(out) as ds:
                if ds.width > 0 and ds.height > 0:
                    print(f"[cache] {name:12s} ({out.stat().st_size / (1024*1024):.1f} MB)")
                    return out
        except Exception:
            pass

    url = _url(coverage, cfg.BBOX_WGS84, stamp, projected, target_crs)
    success = _download(url, out, retries, optional)
    return out if success else None


def fetch_all(
    target_lat: float | None = None,
    target_lon: float | None = None,
    half_deg: float = 0.12,
    client: str | None = None,
    address: str | None = None,
    force: bool = False,
) -> dict[str, Path | None]:
    """Fetch all baseline layers required for analysis engines."""
    if target_lat is not None and target_lon is not None:
        cfg.set_target_site(target_lat, target_lon, half_deg, client, address)

    print("=" * 60)
    print(f"SiteSurveyor AI — Data Acquisition [{cfg.AOI_SLUG}]")
    print(f"Center:    Lat {cfg.TARGET_LAT:.5f}, Lon {cfg.TARGET_LON:.5f}")
    print(f"BBOX:      {cfg.BBOX_WGS84}")
    print(f"Local CRS: {cfg.LOCAL_CRS}")
    print(f"API Key:   {cfg.API_KEY[:8]}..." if cfg.API_KEY else "API Key: NOT SET")
    print("=" * 60)

    use_cache = not force
    results: dict[str, Path | None] = {}

    # 1. Copernicus DEM 30m
    results["dem"] = fetch("dem", "dem_cop_30", cache=use_cache)

    # 2. ESA WorldCover 2021 (10m)
    results["landcover"] = fetch("landcover", "esa_worldcover_2021", cache=use_cache)

    # 3. ALOS PALSAR 2007 L-Band SAR Mosaic
    results["alos"] = fetch("alos", "alos_palsar_mosaic", "2007-01-01T00:00:00.000Z", cache=use_cache)

    # 4. Landsat WOfS (Water Observations from Space)
    results["wofs"] = fetch("wofs", "wofs_ls_summary_alltime", projected=True, cache=use_cache)

    # 5. Sentinel-2 Annual GeoMAD 2023
    results["geomad"] = fetch("geomad", "gm_s2_annual", "2023-01-01T00:00:00.000Z", projected=True, cache=use_cache)

    # 6. CHIRPS Monthly Rainfall (2023-2024 sample)
    months = [(y, m) for y in (2023, 2024) for m in range(1, 13)]
    cube, transform, crs = [], None, None
    for y, m in months:
        f = fetch(f"rain_{y}{m:02d}", "rainfall_chirps_monthly",
                  f"{y}-{m:02d}-01T00:00:00.000Z", optional=True,
                  target_crs="EPSG:4326", projected=False, cache=use_cache)
        if f is not None and f.exists():
            try:
                with rasterio.open(f) as ds:
                    cube.append(ds.read(1).astype("float32"))
                    transform, crs = ds.transform, ds.crs
            except Exception:
                pass

    rain_mean_path = cfg.RAW / "rain_mean.tif"
    if cube and (force or not rain_mean_path.exists()):
        arr = np.nanmean(np.stack(cube), axis=0)
        with rasterio.open(
            rain_mean_path, "w", driver="GTiff",
            height=arr.shape[0], width=arr.shape[1], count=1,
            dtype="float32", crs=crs, transform=transform,
            nodata=np.nan,
        ) as dst:
            dst.write(arr, 1)
        print(f"[ok] rain_mean   Aggregated {len(cube)} months; ~{np.nanmean(arr) * 12:.0f} mm/yr")
    elif rain_mean_path.exists():
        print("[cache] rain_mean")

    results["rain_mean"] = rain_mean_path if rain_mean_path.exists() else None

    # 7. DE Africa Continental Cropland Extent (10m - African Agriculture Model)
    results["crop_mask"] = fetch(
        "crop_mask", "crop_mask", "2019-01-01T00:00:00.000Z",
        projected=True, optional=True, cache=use_cache
    )

    # 8. DE Africa Fractional Cover Annual Summary (Landsat 30m - BS / PV / NPV)
    results["fc_ls"] = fetch(
        "fc_ls_2023", "fc_ls_summary_annual", "2023-01-01T00:00:00.000Z",
        projected=True, optional=True, cache=use_cache
    )

    return results


if __name__ == "__main__":
    os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
    fetch_all()
