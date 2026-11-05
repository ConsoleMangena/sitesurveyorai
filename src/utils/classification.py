"""
SiteSurveyor AI — Classification & Siting Utilities
===================================================
Natural breaks (1-D k-means in pure numpy), potential zone classification,
and distance-constrained local peak picking for candidate borehole/target sites.
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import maximum_filter

import src.config as cfg
from src.utils.raster import pixel_to_lonlat


def jenks_breaks(values: np.ndarray, k: int = 5, max_iter: int = 25) -> np.ndarray:
    """
    Compute natural breaks using 1-D k-means clustering in pure NumPy.
    Returns:
        Sorted array of k - 1 interior break thresholds.
    """
    v = values[np.isfinite(values)].astype("float64")
    if len(v) < k * 5:
        return np.linspace(np.nanmin(v), np.nanmax(v), k + 1)[1:-1].astype("float32")

    # Sample for performance if large
    if len(v) > 25000:
        np.random.seed(42)
        v_sub = np.random.choice(v, 25000, replace=False)
    else:
        v_sub = v

    # Initialize centers as evenly spaced quantiles
    centers = np.quantile(v_sub, np.linspace(0.1, 0.9, k))

    for _ in range(max_iter):
        dists = np.abs(v_sub[:, None] - centers[None, :])
        labels = np.argmin(dists, axis=1)

        new_centers = np.empty(k, dtype="float64")
        for i in range(k):
            mask = (labels == i)
            new_centers[i] = v_sub[mask].mean() if np.any(mask) else centers[i]

        new_centers.sort()
        if np.allclose(centers, new_centers, atol=1e-3):
            break
        centers = new_centers

    breaks = (centers[:-1] + centers[1:]) / 2.0
    return np.sort(breaks).astype("float32")


def classify_zones(
    index_0_100: np.ndarray,
    breaks: np.ndarray,
    water_mask: np.ndarray | None = None,
    builtup_mask: np.ndarray | None = None,
) -> np.ndarray:
    """
    Classify continuous 0-100 index into zones:
        0: Water (excluded)
        1: Very Low
        2: Low
        3: Moderate
        4: High
        5: Very High
        6: Built-up / Settlement (excluded)
    """
    zones = np.digitize(index_0_100, breaks) + 1  # 1 to 5
    zones = np.clip(zones, 1, len(breaks) + 1).astype("uint8")

    if water_mask is not None:
        zones[water_mask] = 0

    if builtup_mask is not None:
        zones[builtup_mask] = 6

    return zones


def find_candidate_sites(
    index_0_100: np.ndarray,
    classes: np.ndarray,
    min_class: int = 4,
    min_distance_m: float = 300.0,
    top_k: int = 8,
    target_row: int | None = None,
    target_col: int | None = None,
    max_distance_km: float | None = None,
    border_margin_px: int = 25,
    proximity_weight: float = 0.08,
) -> list[dict]:
    """
    Find ranked candidate sites using local peak-picking with spatial suppression
    and client proximity prioritization.

    Args:
        index_0_100: Continuous potential index (0-100)
        classes: Discrete zone class raster (0-6)
        min_class: Minimum class required for candidates (default 4 = High)
        min_distance_m: Minimum spatial spacing between candidate sites
        top_k: Maximum number of ranked candidates to return
        target_row: Row index of client property / target
        target_col: Col index of client property / target
        max_distance_km: Optional hard radius constraint (km) from target
        border_margin_px: Exclude pixels near outer raster edges to eliminate boundary artifacts
        proximity_weight: Weight penalty per km distance to prioritize accessible sites near property

    Returns:
        List of dicts with keys: rank, row, col, lon, lat, potential_score, class_name, distance_from_target_km
    """
    if target_row is None:
        target_row = cfg.TARGET_ROW
    if target_col is None:
        target_col = cfg.TARGET_COL

    min_dist_px = int(np.ceil(min_distance_m / cfg.CELL))
    size = min_dist_px * 2 + 1

    eligible = (classes >= min_class) & (classes <= 5) & np.isfinite(index_0_100)

    # Exclude boundary margins to prevent edge artifacts
    if border_margin_px > 0:
        eligible[:border_margin_px, :] = False
        eligible[-border_margin_px:, :] = False
        eligible[:, :border_margin_px] = False
        eligible[:, -border_margin_px:] = False

    # Optional hard distance constraint
    if max_distance_km is not None:
        h, w = index_0_100.shape
        yy, xx = np.indices((h, w))
        dist_all_km = np.hypot(yy - target_row, xx - target_col) * cfg.CELL / 1000.0
        eligible[dist_all_km > max_distance_km] = False

    masked_index = np.where(eligible, index_0_100, -1.0)
    local_max = maximum_filter(masked_index, size=size, mode="constant", cval=-1.0)
    peaks = (masked_index == local_max) & (masked_index > 0)

    rows, cols = np.where(peaks)
    if len(rows) == 0:
        return []

    scores = index_0_100[rows, cols]
    dists_km = np.hypot(rows - target_row, cols - target_col) * cfg.CELL / 1000.0

    # Rank metric: balances high potential score with client proximity
    rank_metrics = scores / (1.0 + proximity_weight * dists_km)
    sort_order = np.argsort(-rank_metrics)

    class_names = {1: "Very low", 2: "Low", 3: "Moderate", 4: "High", 5: "Very high"}

    candidates: list[dict] = []
    selected_coords: list[tuple[int, int]] = []

    for idx in sort_order:
        r, c = int(rows[idx]), int(cols[idx])

        too_close = False
        for sr, sc in selected_coords:
            dist_px = np.hypot(r - sr, c - sc)
            if dist_px * cfg.CELL < min_distance_m:
                too_close = True
                break
        if too_close:
            continue

        selected_coords.append((r, c))
        lon, lat = pixel_to_lonlat(r, c)
        cls_val = int(classes[r, c])

        candidates.append({
            "rank": len(candidates) + 1,
            "row": r,
            "col": c,
            "latitude": round(lat, 5),
            "longitude": round(lon, 5),
            "potential_score": round(float(scores[idx]), 1),
            "class_code": cls_val,
            "class_name": class_names.get(cls_val, "Unknown"),
            "distance_from_target_km": round(float(dists_km[idx]), 2),
        })

        if len(candidates) >= top_k:
            break

    return candidates
