"""Unit tests for the FBA network wrapper and the minimal cell model."""

from __future__ import annotations

import pytest

from vcs_engine.biology import build_minimal_cell_model
from vcs_engine.biology.naming import pool_var

POOL = pool_var("glc")


def test_optimal_growth_with_substrate() -> None:
    net = build_minimal_cell_model(maintenance_atp=1.0, mu_max=1.0)
    sol = net.solve({POOL: 10.0})
    assert sol.is_optimal
    assert sol.growth_rate == pytest.approx(1.0)  # capped at mu_max with abundant substrate


def test_growth_below_cap_is_uptake_limited() -> None:
    # With maintenance m=1 (=> m/10=0.1) and stoichiometry u = 6*mu + m/10,
    # a limit of 3.0 gives mu = (3.0 - 0.1) / 6.
    net = build_minimal_cell_model(maintenance_atp=1.0, mu_max=1.0)
    sol = net.solve({POOL: 3.0})
    assert sol.is_optimal
    assert sol.growth_rate == pytest.approx((3.0 - 0.1) / 6.0)


def test_consumption_is_determined_no_dumping() -> None:
    # Fixed maintenance means uptake is exactly 6*mu + m/10 — surplus substrate is
    # NOT wastefully dumped even when more is available.
    net = build_minimal_cell_model(maintenance_atp=1.0, mu_max=1.0)
    sol = net.solve({POOL: 50.0})
    expected_uptake = 6.0 * sol.growth_rate + 0.1
    assert sol.uptake_fluxes[POOL] == pytest.approx(expected_uptake)
    assert sol.uptake_fluxes[POOL] < 50.0  # did not consume all that was offered


def test_infeasible_below_maintenance() -> None:
    # Uptake below m/10 = 0.1 cannot cover maintenance -> infeasible, no growth.
    net = build_minimal_cell_model(maintenance_atp=1.0, mu_max=1.0)
    sol = net.solve({POOL: 0.05})
    assert not sol.is_optimal
    assert sol.growth_rate == 0.0
    assert sol.uptake_fluxes[POOL] == 0.0


def test_zero_uptake_infeasible() -> None:
    net = build_minimal_cell_model()
    sol = net.solve({POOL: 0.0})
    assert not sol.is_optimal
    assert sol.growth_rate == 0.0
