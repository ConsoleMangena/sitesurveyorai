"""
SiteSurveyor AI — Terrain Utilities
====================================
DEM processing: sink filling, D8 flow accumulation, slope, hillshade,
Topographic Wetness Index (TWI), drainage density, and stream indices.
"""
from __future__ import annotations

import heapq
import numpy as np
from scipy.ndimage import uniform_filter

import src.config as cfg


def fill_sinks(dem: np.ndarray) -> np.ndarray:
    """
    Priority-flood sink filling algorithm (Wang & Liu 2006).
    Ensures all depressions in the DEM are raised to drain out to borders.
    """
    h, w = dem.shape
    filled = np.full((h, w), np.nan, dtype="float32")
    visited = np.zeros((h, w), dtype=bool)
    heap: list[tuple[float, int, int]] = []

    # Initialize border cells into priority queue
    for r in range(h):
        for c in (0, w - 1):
            val = float(dem[r, c])
            if np.isfinite(val):
                heapq.heappush(heap, (val, r, c))
                filled[r, c] = val
                visited[r, c] = True

    for c in range(w):
        for r in (0, h - 1):
            if not visited[r, c]:
                val = float(dem[r, c])
                if np.isfinite(val):
                    heapq.heappush(heap, (val, r, c))
                    filled[r, c] = val
                    visited[r, c] = True

    # Process priority queue
    neighbors = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]
    while heap:
        elev, r, c = heapq.heappop(heap)
        for dr, dc in neighbors:
            nr, nc = r + dr, c + dc
            if 0 <= nr < h and 0 <= nc < w and not visited[nr, nc]:
                visited[nr, nc] = True
                val = float(dem[nr, nc])
                if np.isfinite(val):
                    spill = max(elev, val)
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

    # Clear border cells
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

    return flow_dir, flow_acc


def slope_degrees(dem: np.ndarray) -> np.ndarray:
    """Compute terrain slope in degrees using 2D finite difference gradients."""
    gy, gx = np.gradient(dem, cfg.CELL)
    slope_rad = np.arctan(np.hypot(gx, gy))
    return np.degrees(slope_rad)


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
    return np.clip(hs, 0.0, 1.0).astype("float32")


def twi(filled: np.ndarray, slope_deg_arr: np.ndarray, flow_acc: np.ndarray | None = None) -> np.ndarray:
    """
    Compute Topographic Wetness Index:
        TWI = ln(As / tan(beta))
    where As is specific catchment area (m) and beta is slope in radians.
    """
    if flow_acc is None:
        _, flow_acc = d8_flow(filled)

    # Specific catchment area per unit contour length
    specific_area = flow_acc * cfg.CELL
    slope_rad = np.radians(np.maximum(slope_deg_arr, 0.1))
    tan_slope = np.maximum(np.tan(slope_rad), 0.001)

    twi_val = np.log(specific_area / tan_slope)
    return np.maximum(twi_val, 0.0).astype("float32")


def drainage_density(flow_acc: np.ndarray, threshold: int = 500, kernel_radius: int = 17) -> np.ndarray:
    """
    Extract channel network where flow_acc > threshold and compute drainage density (km/km2).
    """
    streams = (flow_acc > threshold).astype("float32")
    size = kernel_radius * 2 + 1
    # Mean stream fraction within the neighborhood window
    density = uniform_filter(streams, size=size, mode="reflect")
    # Convert cell count fraction to km per km2:
    # In each cell (30x30m), a stream pixel represents ~30m of stream length.
    # Total area per cell = 900 m2. density (fraction) * (0.03 km / 0.0009 km2) = density * 33.3 km/km2
    km_per_km2 = density * (cfg.CELL / 1000.0) / ((cfg.CELL * cfg.CELL) / 1e6)
    return km_per_km2.astype("float32")


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

