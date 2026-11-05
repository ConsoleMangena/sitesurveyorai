"""
SiteSurveyor AI — Terrain Utilities
====================================
DEM processing: sink filling, D8 flow accumulation, slope, hillshade,
Topographic Wetness Index (TWI), drainage density, and stream indices.
"""
from __future__ import annotations

import heapq
import numpy as np
from scipy.ndimage import binary_dilation, uniform_filter

import src.config as cfg

# Wang & Liu (2006) epsilon: the smallest fill increment that survives float32
# on ~1 km elevations. It gives true plateaus a monotone micro-slope (about
# 0.002 degrees per 30 m cell) so flow routing never dead-ends in a flat.
FILL_EPSILON_M = 1e-3


def fill_sinks(dem: np.ndarray) -> np.ndarray:
    """
    Priority-flood sink filling (Wang & Liu 2006).

    Depressions are raised until every cell can drain to an outlet. Outlets are
    the array border and the rim of every data void, so valid terrain walled in
    by missing data is still filled instead of being silently dropped.
    """
    h, w = dem.shape
    filled = np.full((h, w), np.nan, dtype="float32")
    visited = np.zeros((h, w), dtype=bool)
    heap: list[tuple[float, int, int]] = []

    valid = np.isfinite(dem)
    border = np.zeros((h, w), dtype=bool)
    border[0, :] = True
    border[-1, :] = True
    border[:, 0] = True
    border[:, -1] = True
    void_rim = binary_dilation(~valid, structure=np.ones((3, 3), dtype=bool))
    seeds = np.argwhere(valid & (border | void_rim))

    for r, c in seeds:
        val = float(dem[r, c])
        filled[r, c] = val
        visited[r, c] = True
        heapq.heappush(heap, (val, int(r), int(c)))

    neighbors = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]
    while heap:
        elev, r, c = heapq.heappop(heap)
        for dr, dc in neighbors:
            nr, nc = r + dr, c + dc
            if 0 <= nr < h and 0 <= nc < w and not visited[nr, nc]:
                visited[nr, nc] = True
                val = float(dem[nr, nc])
                if np.isfinite(val):
                    spill = max(elev, val) + FILL_EPSILON_M
                    filled[nr, nc] = spill
                    heapq.heappush(heap, (spill, nr, nc))

    return filled


def d8_flow(filled: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute D8 steepest downhill flow direction and flow accumulation.

    Returns:
        flow_dir: (H, W) int8 direction (0..7), -1 for pit/boundary
        flow_acc: (H, W) float32 upstream cell accumulation count
    """
    h, w = filled.shape
    flow_dir = np.full((h, w), -1, dtype="int8")
    flow_acc = np.ones((h, w), dtype="float32")

    # D8 neighbor offsets (dr, dc) and distances
    d8_offsets = [
        (0, 1),   # 0: E
        (1, 1),   # 1: SE
        (1, 0),   # 2: S
        (1, -1),  # 3: SW
        (0, -1),  # 4: W
        (-1, -1), # 5: NW
        (-1, 0),  # 6: N
        (-1, 1),  # 7: NE
    ]
    dist = [cfg.CELL if dr == 0 or dc == 0 else cfg.CELL * 1.41421356 for dr, dc in d8_offsets]

    # Vectorized steepest downslope calculation across all 8 D8 directions
    slopes = np.full((8, h, w), -1e9, dtype="float32")
    for k, ((dr, dc), d) in enumerate(zip(d8_offsets, dist)):
        r_src = slice(max(0, -dr), min(h, h - dr))
        c_src = slice(max(0, -dc), min(w, w - dc))
        r_dst = slice(max(0, dr), min(h, h + dr))
        c_dst = slice(max(0, dc), min(w, w + dc))

        diff = filled[r_src, c_src] - filled[r_dst, c_dst]
        valid_pair = np.isfinite(filled[r_src, c_src]) & np.isfinite(filled[r_dst, c_dst])
        slopes[k, r_src, c_src] = np.where(valid_pair, diff / d, -1e9)

    max_slope = np.max(slopes, axis=0)
    best_dir = np.argmax(slopes, axis=0).astype("int8")
    flow_dir = np.where(max_slope > 0, best_dir, -1).astype("int8")

    # Border cells are outflow boundaries: they keep everything they receive but
    # pass nothing on, so accumulation is complete up to the edge of the AOI and
    # any channel that leaves the window is truncated there.
    flow_dir[0, :] = -1
    flow_dir[-1, :] = -1
    flow_dir[:, 0] = -1
    flow_dir[:, -1] = -1

    # Accumulate flow by sorting pixels by elevation in descending order
    valid = np.isfinite(filled)
    coords = np.argwhere(valid)
    elevs = filled[valid]
    sort_idx = np.argsort(-elevs)  # Highest to lowest

    for idx in sort_idx:
        r, c = coords[idx]
        d = flow_dir[r, c]
        if d >= 0:
            dr, dc = d8_offsets[d]
            nr, nc = r + dr, c + dc
            if 0 <= nr < h and 0 <= nc < w:
                flow_acc[nr, nc] += flow_acc[r, c]

    # A data void has no catchment. Leaving it at 1 would read as "a dry slope".
    flow_acc[~valid] = np.nan

    return flow_dir, flow_acc


def _stencil_reaches_void(dem: np.ndarray) -> np.ndarray:
    """
    Cells whose finite-difference stencil touches a data void.

    np.gradient takes the central difference (f[i+1] - f[i-1]) / 2h, which skips
    the sample in the middle: a lone void would otherwise report as flat ground
    and then be used as evidence.
    """
    return binary_dilation(~np.isfinite(dem), structure=np.ones((3, 3), dtype=bool))


def slope_degrees(dem: np.ndarray) -> np.ndarray:
    """Compute terrain slope in degrees using 2D finite difference gradients."""
    gy, gx = np.gradient(dem, cfg.CELL)
    slope_rad = np.arctan(np.hypot(gx, gy))
    slope = np.degrees(slope_rad).astype("float32")
    slope[_stencil_reaches_void(dem)] = np.nan
    return slope


def terrain_hillshade(dem: np.ndarray, az: float = 315.0, alt: float = 45.0) -> np.ndarray:
    """
    Compute analytical shaded relief (hillshade) normalized to [0, 1].
    """
    gy, gx = np.gradient(dem, cfg.CELL)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)

    az_rad = np.radians(az)
    alt_rad = np.radians(alt)

    hs = np.sin(alt_rad) * np.cos(slope) + np.cos(alt_rad) * np.sin(slope) * np.cos(az_rad - aspect)
    hs = np.clip(hs, 0.0, 1.0).astype("float32")
    hs[_stencil_reaches_void(dem)] = np.nan
    return hs


def twi(filled: np.ndarray, slope_deg_arr: np.ndarray, flow_acc: np.ndarray | None = None) -> np.ndarray:
    """
    Compute Topographic Wetness Index:
        TWI = ln(As / tan(beta))
    where As is specific catchment area (m) and beta is slope in radians.

    Pass the slope of the *filled* surface: routing flow over sinks while
    measuring slope on the unfilled DEM puts the two terms of the ratio on
    different surfaces. Slope is floored at 0.1 degrees because tan(0) would
    divide by zero on true flats; negative TWI is kept, as on steep dry slopes
    the index is legitimately below zero.
    """
    if flow_acc is None:
        _, flow_acc = d8_flow(filled)

    # Specific catchment area per unit contour length
    specific_area = flow_acc * cfg.CELL
    slope_rad = np.radians(np.maximum(slope_deg_arr, 0.1))
    tan_slope = np.maximum(np.tan(slope_rad), 0.001)

    return np.log(specific_area / tan_slope).astype("float32")


def drainage_density(
    flow_acc: np.ndarray,
    threshold: int = 500,
    kernel_radius: int = 17,
    valid_mask: np.ndarray | None = None,
    min_observed_fraction: float = 0.34,
) -> np.ndarray:
    """
    Extract channel network where flow_acc > threshold and compute drainage
    density in km/km² of observed surface.

    Windows dominated by data voids return NaN: an area the DEM does not cover
    is not an area with no streams.
    """
    streams = np.where(np.isfinite(flow_acc), flow_acc > threshold, 0.0).astype("float32")
    size = kernel_radius * 2 + 1

    observed = (
        np.ones_like(streams)
        if valid_mask is None
        else np.asarray(valid_mask, dtype="float32")
    )
    fraction = uniform_filter(streams, size=size, mode="reflect")
    obs_fraction = uniform_filter(observed, size=size, mode="reflect")

    # Each stream cell stands for CELL metres of channel inside CELL² metres of ground.
    km_per_km2 = (cfg.CELL / 1000.0) / ((cfg.CELL * cfg.CELL) / 1e6)
    density = np.where(
        obs_fraction >= min_observed_fraction,
        fraction / np.maximum(obs_fraction, 1e-6) * km_per_km2,
        np.nan,
    )
    return density.astype("float32")


def stream_power_index(flow_acc: np.ndarray, slope_deg_arr: np.ndarray) -> np.ndarray:
    """Stream Power Index (SPI) = As * tan(beta). Indicator of erosion scouring potential."""
    specific_area = flow_acc * cfg.CELL
    tan_slope = np.tan(np.radians(np.maximum(slope_deg_arr, 0.1)))
    return (specific_area * tan_slope).astype("float32")


def sediment_transport_index(flow_acc: np.ndarray, slope_deg_arr: np.ndarray) -> np.ndarray:
    """Sediment Transport Index (STI) = (As / 22.13)^0.6 * (sin(beta) / 0.0896)^1.3."""
    as_norm = np.maximum(flow_acc * cfg.CELL / 22.13, 0.0)
    sin_norm = np.maximum(np.sin(np.radians(slope_deg_arr)) / 0.0896, 0.0)
    return ((as_norm ** 0.6) * (sin_norm ** 1.3)).astype("float32")

