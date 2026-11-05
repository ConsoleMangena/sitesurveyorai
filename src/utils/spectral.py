"""
SiteSurveyor AI — Spectral Utilities
=====================================
Multi-spectral and alteration index algorithms for Sentinel-2 / ASTER:
NDVI, NDMI, NDWI, Iron Oxide, Hydroxyl/Clay, Ferrous, Gossan, and
vegetation residual regression.
"""
from __future__ import annotations

import numpy as np


def ndvi(nir: np.ndarray, red: np.ndarray) -> np.ndarray:
    """Normalized Difference Vegetation Index = (NIR - Red) / (NIR + Red)."""
    denom = nir + red
    idx = np.where(denom != 0, (nir - red) / denom, np.nan)
    return np.clip(idx, -1.0, 1.0).astype("float32")


def ndmi(nir: np.ndarray, swir1: np.ndarray) -> np.ndarray:
    """Normalized Difference Moisture Index = (NIR - SWIR1) / (NIR + SWIR1)."""
    denom = nir + swir1
    idx = np.where(denom != 0, (nir - swir1) / denom, np.nan)
    return np.clip(idx, -1.0, 1.0).astype("float32")


def ndwi(green: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """Normalized Difference Water Index = (Green - NIR) / (Green + NIR)."""
    denom = green + nir
    idx = np.where(denom != 0, (green - nir) / denom, np.nan)
    return np.clip(idx, -1.0, 1.0).astype("float32")


def iron_oxide_index(red: np.ndarray, blue: np.ndarray) -> np.ndarray:
    """Iron Oxide Index = (Red - Blue) / (Red + Blue) or Red / Blue."""
    denom = red + blue
    idx = np.where(denom != 0, (red - blue) / denom, np.nan)
    return np.clip(idx, -1.0, 1.0).astype("float32")


def gossan_index(swir1: np.ndarray, red: np.ndarray, blue: np.ndarray) -> np.ndarray:
    """Gossan Index = (SWIR1 / Red) * (Red / Blue). Weathered sulfide indicator."""
    ratio1 = np.where(red > 0.001, swir1 / red, np.nan)
    ratio2 = np.where(blue > 0.001, red / blue, np.nan)
    idx = ratio1 * ratio2
    return idx.astype("float32")


def hydroxyl_index(swir1: np.ndarray, swir2: np.ndarray) -> np.ndarray:
    """Hydroxyl / Clay Alteration Index = (SWIR1 - SWIR2) / (SWIR1 + SWIR2)."""
    denom = swir1 + swir2
    idx = np.where(denom != 0, (swir1 - swir2) / denom, np.nan)
    return np.clip(idx, -1.0, 1.0).astype("float32")


def ferrous_index(swir1: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """Ferrous / Mafic Silicate Index = (SWIR1 - NIR) / (SWIR1 + NIR)."""
    denom = swir1 + nir
    idx = np.where(denom != 0, (swir1 - nir) / denom, np.nan)
    return np.clip(idx, -1.0, 1.0).astype("float32")


def bare_soil_index(red: np.ndarray, swir1: np.ndarray, nir: np.ndarray, blue: np.ndarray) -> np.ndarray:
    """Bare Soil Index (BSI) = ((SWIR1 + Red) - (NIR + Blue)) / ((SWIR1 + Red) + (NIR + Blue))."""
    numer = (swir1 + red) - (nir + blue)
    denom = (swir1 + red) + (nir + blue)
    idx = np.where(denom != 0, numer / denom, np.nan)
    return np.clip(idx, -1.0, 1.0).astype("float32")


def residual_index(index_arr: np.ndarray, ndvi_arr: np.ndarray, deg: int = 2) -> np.ndarray:
    """
    Remove vegetation influence from mineral / moisture indices using polynomial regression.
    Residual = Observed Index - Predicted Index(NDVI).
    """
    valid = np.isfinite(index_arr) & np.isfinite(ndvi_arr)
    if np.sum(valid) < 100:
        return index_arr

    x = ndvi_arr[valid]
    y = index_arr[valid]

    # Sample for robust polynomial fitting if array is large
    if len(x) > 50000:
        sample_idx = np.random.choice(len(x), 50000, replace=False)
        xs, ys = x[sample_idx], y[sample_idx]
    else:
        xs, ys = x, y

    coeffs = np.polyfit(xs, ys, deg=deg)
    pred = np.polyval(coeffs, ndvi_arr)

    residual = index_arr - pred
    return residual.astype("float32")

