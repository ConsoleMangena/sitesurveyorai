"""
SiteSurveyor AI — Lineament Utilities
======================================
Automated fracture and lineament detection from SAR backscatter and DEM hillshade:
Canny edge detection, Probabilistic Hough Transform, lineament density (km/km²),
lineament intersections (>20° disparity), and strike azimuth analysis.
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import uniform_filter
from skimage.draw import line as draw_line
from skimage.feature import canny
from skimage.transform import probabilistic_hough_line

import src.config as cfg
from src.utils.raster import robust_norm


def extract_edges(sar_hv: np.ndarray, hillshade: np.ndarray) -> np.ndarray:
    """
    Extract multi-source structural edges by fusing SAR backscatter and DEM hillshade.
    """
    # Normalize SAR HV backscatter
    sar_clean = np.nan_to_num(robust_norm(sar_hv, 2, 98), nan=0.0)
    hs_clean = np.nan_to_num(hillshade, nan=0.0)

    # Canny on both layers
    e_sar = canny(sar_clean, sigma=1.5, low_threshold=0.10, high_threshold=0.25)
    e_dem = canny(hs_clean, sigma=1.5, low_threshold=0.12, high_threshold=0.29)

    return e_sar | e_dem


def detect_lineaments(
    edge_mask: np.ndarray,
    threshold: int = 25,
    min_length_px: int = 30,
    line_gap_px: int = 5,
    min_length_meters: float = 600.0,
) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """
    Extract linear structural segments using Probabilistic Hough Transform.
    Filters out noise and micro-features, preserving regional structural fractures.

    Returns:
        List of segments: [((col0, row0), (col1, row1)), ...]
    """
    raw_segs = probabilistic_hough_line(
        edge_mask,
        threshold=threshold,
        line_length=min_length_px,
        line_gap=line_gap_px,
        rng=42,
    )

    valid_segs: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for (c0, r0), (c1, r1) in raw_segs:
        dx = (c1 - c0) * cfg.CELL
        dy = (r1 - r0) * cfg.CELL
        length = np.hypot(dx, dy)
        if length >= min_length_meters:
            valid_segs.append(((c0, r0), (c1, r1)))

    return valid_segs


def segment_azimuths(segments: list[tuple[tuple[int, int], tuple[int, int]]]) -> np.ndarray:
    """
    Calculate strike azimuths (0..180 degrees) for lineament segments.
    """
    azimuths = []
    for (c0, r0), (c1, r1) in segments:
        dx = (c1 - c0) * cfg.CELL
        dy = -(r1 - r0) * cfg.CELL  # Invert row axis so north is up
        angle = np.degrees(np.arctan2(dx, dy)) % 180.0
        azimuths.append(angle)
    return np.array(azimuths, dtype="float32")


def lineament_density(
    segments: list[tuple[tuple[int, int], tuple[int, int]]],
    kernel_radius_px: int = 17,
) -> np.ndarray:
    """
    Rasterize lineaments and calculate lineament density in km/km².
    """
    line_grid = np.zeros((cfg.HEIGHT, cfg.WIDTH), dtype="float32")

    for (c0, r0), (c1, r1) in segments:
        rr, cc = draw_line(r0, c0, r1, c1)
        valid = (rr >= 0) & (rr < cfg.HEIGHT) & (cc >= 0) & (cc < cfg.WIDTH)
        line_grid[rr[valid], cc[valid]] = 1.0

    # Moving average over spatial neighborhood
    size = kernel_radius_px * 2 + 1
    fraction = uniform_filter(line_grid, size=size, mode="reflect")

    # Convert cell count fraction to km of line per km² of area
    # Each cell represents ~30m length in 900m2 area -> factor = 33.33 km/km2
    density = fraction * (cfg.CELL / 1000.0) / ((cfg.CELL * cfg.CELL) / 1e6)
    return density.astype("float32")


def lineament_intersections(
    segments: list[tuple[tuple[int, int], tuple[int, int]]],
    min_angle_diff: float = 20.0,
    kernel_radius_px: int = 17,
) -> tuple[np.ndarray, list[tuple[float, float]]]:
    """
    Find intersection points between lineaments with angular disparity > min_angle_diff.
    Returns:
        intersection_density: (H, W) raster of intersection density
        pts: List of (col, row) coordinates of intersection nodes
    """
    inter_grid = np.zeros((cfg.HEIGHT, cfg.WIDTH), dtype="float32")
    pts: list[tuple[float, float]] = []

    def line_intersection(p1, p2, p3, p4):
        x1, y1 = p1
        x2, y2 = p2
        x3, y3 = p3
        x4, y4 = p4
        denom = (y4 - y3) * (x2 - x1) - (x4 - x3) * (y2 - y1)
        if abs(denom) < 1e-6:
            return None
        ua = ((x4 - x3) * (y1 - y3) - (y4 - y3) * (x1 - x3)) / denom
        ub = ((x2 - x1) * (y1 - y3) - (y2 - y1) * (x1 - x3)) / denom
        if 0.0 <= ua <= 1.0 and 0.0 <= ub <= 1.0:
            return x1 + ua * (x2 - x1), y1 + ua * (y2 - y1)
        return None

    azimuths = segment_azimuths(segments)

    # Precalculate segment bounding boxes for rapid pruning
    bboxes = [
        (min(c0, c1), min(r0, r1), max(c0, c1), max(r0, r1))
        for (c0, r0), (c1, r1) in segments
    ]

    for i in range(len(segments)):
        b1 = bboxes[i]
        for j in range(i + 1, len(segments)):
            b2 = bboxes[j]
            # Rapid bounding box rejection
            if b1[2] < b2[0] or b2[2] < b1[0] or b1[3] < b2[1] or b2[3] < b1[1]:
                continue

            # Check angular disparity
            diff = abs(azimuths[i] - azimuths[j])
            if diff > 90.0:
                diff = 180.0 - diff
            if diff < min_angle_diff:
                continue

            pt = line_intersection(segments[i][0], segments[i][1], segments[j][0], segments[j][1])
            if pt is not None:
                c, r = pt
                ri, ci = int(round(r)), int(round(c))
                if 0 <= ri < cfg.HEIGHT and 0 <= ci < cfg.WIDTH:
                    inter_grid[ri, ci] += 1.0
                    pts.append((c, r))

    size = kernel_radius_px * 2 + 1
    density = uniform_filter(inter_grid, size=size, mode="reflect")
    # Intersections per km²
    area_km2 = (size * cfg.CELL / 1000.0) ** 2
    density_km2 = (density * (size * size)) / area_km2
    return density_km2.astype("float32"), pts

