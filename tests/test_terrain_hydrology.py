"""
Flow-routing invariants for the terrain primitives.

Sink filling, D8 accumulation and TWI feed every water, soil and hazard score,
so these tests check the physical properties that must hold: a closed basin
drains, a plateau has no pits, accumulation is conserved, and data voids stay
voids instead of becoming "dry" or "unfilled" terrain.
"""
from __future__ import annotations

import numpy as np
import pytest

import src.config as cfg
from src.utils.terrain import (
    d8_flow,
    drainage_density,
    fill_sinks,
    slope_degrees,
    twi,
)


@pytest.fixture(autouse=True)
def cell_size(monkeypatch):
    monkeypatch.setattr(cfg, "CELL", 30.0, raising=False)


def test_closed_basin_is_raised_until_it_drains():
    dem = np.full((21, 21), 10.0, dtype="float32")
    dem[8:13, 8:13] = 5.0  # depression with no outlet

    filled = fill_sinks(dem)
    direction, acc = d8_flow(filled)

    assert filled[10, 10] >= 10.0, "sill was not overtopped"
    assert np.isfinite(filled).all()

    valid = np.isfinite(filled)
    sinks = (direction < 0) & valid
    # Every cell contributes its own unit exactly once, so what reaches the
    # sinks must equal the number of cells that produced flow.
    assert acc[sinks].sum() == pytest.approx(valid.sum())


def test_plateau_gets_no_pits():
    dem = np.full((15, 15), 100.0, dtype="float32")

    filled = fill_sinks(dem)
    direction, _ = d8_flow(filled)

    interior = np.zeros((15, 15), dtype=bool)
    interior[1:-1, 1:-1] = True
    assert np.all(direction[interior] >= 0), "flat terrain dead-ended in a pit"
    # The epsilon ramp must stay a rounding artefact, not a fabricated relief.
    assert (filled.max() - filled.min()) < 0.05


def test_terrain_beyond_a_data_void_is_still_filled():
    dem = np.zeros((21, 21), dtype="float32")
    dem += np.linspace(0.0, 4.0, 21)[None, :]
    dem[:, 10] = np.nan  # no-data band splitting the scene

    filled = fill_sinks(dem)
    direction, acc = d8_flow(filled)

    assert np.isfinite(filled[:, 11:]).all(), "valid cells behind a void were dropped"
    assert np.isnan(acc[:, 10]).all(), "void cells were given a catchment"
    assert np.isnan(filled[:, 10]).all()


def test_twi_keeps_negative_values_on_steep_slopes():
    filled = np.full((5, 5), 500.0, dtype="float32")
    steep = np.full((5, 5), 89.0, dtype="float32")
    dry = np.ones((5, 5), dtype="float32")

    index = twi(filled, steep, flow_acc=dry)

    # As = 30 m, tan(89 deg) = 57 -> ln(30/57) is negative, and a dry steep
    # slope must stay distinguishable from a merely steep one.
    assert np.all(index < 0)
    assert np.all(np.isfinite(index))


def test_twi_propagates_missing_slope_and_coverage():
    filled = np.full((5, 5), 10.0, dtype="float32")
    slope = np.full((5, 5), 2.0, dtype="float32")
    acc = np.full((5, 5), 10.0, dtype="float32")
    slope[0, 0] = np.nan
    acc[4, 4] = np.nan

    index = twi(filled, slope, flow_acc=acc)

    assert np.isnan(index[0, 0])
    assert np.isnan(index[4, 4])
    assert np.isfinite(index[2, 2])


def test_twi_on_flats_is_finite_and_peaks_in_the_valley():
    cross = np.abs(np.arange(21) - 10).astype("float32") * 2.0
    dem = np.tile(cross[None, :], (21, 1)) + np.linspace(6.0, 0.0, 21)[:, None]

    filled = fill_sinks(dem)
    index = twi(filled, slope_degrees(filled))

    assert np.isfinite(index).all(), "tan(beta) floor failed on a flat"
    valley = index[:, 10].mean()
    ridge = index[:, 0].mean()
    assert valley > ridge, "TWI did not concentrate in the valley bottom"


def test_drainage_density_reports_voids_instead_of_zero():
    acc = np.full((40, 40), 100.0, dtype="float32")
    acc[20:, :] = 600.0  # channel network over the lower half

    valid = np.ones((40, 40), dtype=bool)
    valid[:8, :8] = False

    dens = drainage_density(acc, threshold=500, kernel_radius=3, valid_mask=valid)

    assert np.isnan(dens[0, 0]), "uncovered window published as zero drainage"
    assert dens[30, 30] > dens[5, 30], "channelised ground read as barren"

    full = drainage_density(acc, threshold=500, kernel_radius=3)
    assert np.isfinite(full).all()
    assert dens[30, 30] == pytest.approx(full[30, 30], rel=1e-5)


def test_slope_is_zero_on_a_flat_and_voids_stay_void():
    dem = np.full((9, 9), 250.0, dtype="float32")
    dem[4, 4] = np.nan

    slope = slope_degrees(dem)

    assert slope[0, 0] == pytest.approx(0.0)
    assert np.isnan(slope[4, 4])
    assert np.isnan(slope[3, 4]), "gradient must not invent slope beside a void"
