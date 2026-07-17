"""Tests for the pharmacology (Drug Interaction Studio) engine layer.

Two guarantees matter most:
1. A drug-free run is *bit-for-bit* identical to before (the golden trajectory test
   covers the general case; here we assert an explicit control-vs-empty-regimen match).
2. Every drug effect is a real change to an existing simulation variable, deterministic
   and dose-dependent.
"""

from __future__ import annotations

from vcs_engine.biology import build_lifecycle_scenario
from vcs_engine.biology.naming import (
    MASS,
    MEMBRANE_INTEGRITY,
    MEMBRANE_LIPID,
    MEMBRANE_PROTEIN,
    drug_var,
)
from vcs_engine.pharmacology import (
    CHANNELS,
    DRUG_LIBRARY,
    MEMBRANE_LYSIS,
    DrugDose,
    DrugRegimen,
    channel_modifiers,
)
from vcs_engine.pharmacology.library import MULTIPLIER_CHANNELS, effective_dose, pk_fraction


def _run(regimen: DrugRegimen | None, *, steps: int = 120, dt: float = 0.1, seed: int = 7):
    state, scheduler = build_lifecycle_scenario(seed=seed, drug_regimen=regimen)
    masses = []
    for _ in range(steps):
        scheduler.step(dt)
        masses.append(state.get(MASS))
    return state, masses


# --------------------------------------------------------------- library shape
def test_library_has_ten_drugs_with_valid_channels() -> None:
    assert len(DRUG_LIBRARY) >= 10
    viz = {"membrane", "ribosome", "dna", "protein", "transport", "signalling", "cytoplasm"}
    for spec in DRUG_LIBRARY.values():
        assert spec.channel_effects, spec.id
        assert set(spec.channel_effects).issubset(set(CHANNELS)), spec.id
        assert spec.viz_target in viz, spec.id
        assert spec.confidence in {"high", "medium", "low"}, spec.id
        assert spec.color.startswith("#"), spec.id


# --------------------------------------------------------------- channel maths
def test_no_drugs_is_identity() -> None:
    mods = channel_modifiers(DrugRegimen(), time=1.0)
    for ch in MULTIPLIER_CHANNELS:
        assert mods[ch] == 1.0
    assert mods[MEMBRANE_LYSIS] == 0.0


def test_dose_scales_effect_and_combines() -> None:
    reg = DrugRegimen((DrugDose("nutrient-transport-inhibitor", dose=1.0, start_time=0.0),))
    full = channel_modifiers(reg, time=10.0)["transport"]
    half = channel_modifiers(
        DrugRegimen((DrugDose("nutrient-transport-inhibitor", dose=0.5),)), time=10.0
    )["transport"]
    assert 0.0 <= full < half < 1.0  # more dose ⇒ stronger inhibition
    # Two multiplier drugs on different channels are independent; same channel multiplies.
    combo = channel_modifiers(
        DrugRegimen((DrugDose("nutrient-transport-inhibitor"), DrugDose("atp-synthesis-inhibitor"))),
        time=10.0,
    )
    assert combo["transport"] < 1.0 and combo["metabolism"] < 1.0


def test_pharmacokinetics_ramp_and_washout() -> None:
    dose = DrugDose("ribosome-inhibitor", dose=1.0, start_time=2.0, duration=5.0)
    assert pk_fraction(dose, 1.0) == 0.0          # before onset
    assert pk_fraction(dose, 2.0) == 0.0          # at start, ramp begins
    assert 0.0 < pk_fraction(dose, 2.25) < 1.0    # ramping
    assert pk_fraction(dose, 5.0) == 1.0          # plateau
    assert pk_fraction(dose, 8.5) == 0.0          # washed out after duration
    assert effective_dose(dose, 1.0) == 0.0


# ------------------------------------------------------------- engine coupling
def test_drug_free_run_matches_empty_regimen() -> None:
    """No regimen and an empty regimen produce the identical trajectory (bit-for-bit)."""
    _, control = _run(None)
    _, empty = _run(DrugRegimen())
    assert control == empty


def test_transport_inhibitor_reduces_growth() -> None:
    _, control = _run(None)
    _, treated = _run(DrugRegimen((DrugDose("nutrient-transport-inhibitor", dose=1.0),)))
    # Blocking uptake starves the cell ⇒ it builds materially less biomass.
    assert treated[-1] < control[-1] * 0.8


def test_membrane_disruptor_degrades_envelope_to_rupture() -> None:
    # Over a full course the disruptor degrades membrane material and collapses integrity
    # to rupture — a qualitatively different fate from the untreated cell.
    treated, _ = _run(DrugRegimen((DrugDose("membrane-disruptor", dose=2.0),)), steps=300)
    control, _ = _run(None, steps=300)
    treated_material = treated.get(MEMBRANE_LIPID, 0) + treated.get(MEMBRANE_PROTEIN, 0)
    control_material = control.get(MEMBRANE_LIPID, 0) + control.get(MEMBRANE_PROTEIN, 0)
    assert treated.get(MEMBRANE_INTEGRITY, 1.0) < 0.3            # ruptured / near-collapse
    assert treated.get(MEMBRANE_INTEGRITY, 1.0) < control.get(MEMBRANE_INTEGRITY, 1.0)
    assert treated_material < control_material * 0.5             # envelope degraded away
    assert treated.get(drug_var("membrane_lysis"), 0.0) > 0.0   # wiring live


def test_drug_variables_are_set_and_deterministic() -> None:
    reg = DrugRegimen((DrugDose("nutrient-transport-inhibitor", dose=1.0),))
    s1, m1 = _run(reg)
    s2, m2 = _run(reg)
    assert m1 == m2  # deterministic
    assert s1.get(drug_var("transport"), 1.0) < 1.0  # the modifier is live on the state


def test_empty_drug_module_is_bit_for_bit() -> None:
    """Attaching the module with an EMPTY regimen (so a run is injectable) is a no-op —
    every channel stays at 1.0 and the trajectory is identical to a module-free run."""
    _, control = _run(None)
    _, empty_module = _run(DrugRegimen())  # empty regimen now DOES register the module
    assert control == empty_module


def test_set_regimen_injects_live() -> None:
    """A drug added mid-run via set_regimen takes effect immediately (real-time injection)."""
    state, scheduler = build_lifecycle_scenario(seed=7, drug_regimen=DrugRegimen())
    mod = next(m for m in scheduler.modules if m.name == "pharmacology")
    for _ in range(20):
        scheduler.step(0.1)
    assert state.get(drug_var("transport"), 1.0) == 1.0  # untreated so far
    mod.set_regimen(
        DrugRegimen((DrugDose("nutrient-transport-inhibitor", dose=1.0, start_time=state.time),))
    )
    for _ in range(20):
        scheduler.step(0.1)
    assert state.get(drug_var("transport"), 1.0) < 1.0  # now inhibited from the injection time
