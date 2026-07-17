"""Flux Balance Analysis (FBA) network wrapper over COBRApy.

This is the metabolism *solver* layer. It wraps a COBRApy model behind a small,
stable interface so the rest of the engine never touches cobra directly and can
later swap in genome-scale SBML models without changing the metabolism module.

Why FBA (constraint-based) rather than kinetic ODEs
---------------------------------------------------
Metabolism is assumed to be at quasi-steady state on the timescale of a growth
step: internal metabolites are balanced (production = consumption) and the cell
allocates fluxes to maximise a biomass objective, subject to uptake constraints.
FBA solves exactly this as a linear program — it is genome-scalable and needs only
stoichiometry plus bounds, not the thousands of kinetic parameters a full kinetic
model would demand. This is the standard method in the field (COBRA/BiGG).

``cobra`` is imported lazily so importing the biology package (Environment /
Transport) does not require the FBA stack.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any, Mapping

from .naming import pool_var


@dataclass(frozen=True)
class FBASolution:
    """Result of one FBA solve.

    Attributes:
        status: Solver status (``"optimal"`` when a solution was found).
        growth_rate: Biomass-objective flux (per hour); ``0`` if not optimal.
        uptake_fluxes: Realised uptake flux per internal pool variable
            (mmol per gDW per hour).
    """

    status: str
    growth_rate: float
    uptake_fluxes: Mapping[str, float]

    @property
    def is_optimal(self) -> bool:
        """True when the solve returned an optimal, growing solution path."""
        return self.status == "optimal"


class MetabolicNetwork:
    """A COBRApy model plus the wiring the engine needs to drive it.

    Args:
        model: A ``cobra.Model`` with an objective set to the biomass reaction.
        biomass_reaction: Reaction id of the biomass objective.
        uptake_reactions: Map of internal pool variable (``met.<species>``) to the
            model reaction whose upper bound represents that nutrient's uptake
            capacity for the step.
    """

    def __init__(
        self,
        model: Any,
        *,
        biomass_reaction: str,
        uptake_reactions: Mapping[str, str],
    ) -> None:
        self.model = model
        self.biomass_reaction = biomass_reaction
        self.uptake_reactions = dict(uptake_reactions)
        #: Base biomass-flux cap (μ_max); scaled per solve by ``growth_scale``.
        self.base_growth_bound = float(model.reactions.get_by_id(biomass_reaction).upper_bound)

    @property
    def pool_variables(self) -> tuple[str, ...]:
        """Internal pool variables this network can consume."""
        return tuple(self.uptake_reactions)

    def solve(
        self, uptake_limits: Mapping[str, float], *, growth_scale: float = 1.0
    ) -> FBASolution:
        """Set uptake upper bounds and maximise biomass.

        Args:
            uptake_limits: Max uptake rate per pool variable (mmol per gDW per hour).
                Missing entries default to 0 (no uptake). Negative values clamp to 0.
            growth_scale: Multiplier on the biomass-flux cap (μ_max), used to express
                a heritable/regulated metabolic-capacity phenotype. Clamps to ≥ 0.

        Returns:
            An :class:`FBASolution`. On any non-optimal status (e.g. the cell cannot
            meet maintenance from the available substrate ⇒ infeasible) growth and
            uptake fluxes are all zero.
        """
        for pool, reaction_id in self.uptake_reactions.items():
            limit = max(0.0, float(uptake_limits.get(pool, 0.0)))
            self.model.reactions.get_by_id(reaction_id).upper_bound = limit
        self.model.reactions.get_by_id(self.biomass_reaction).upper_bound = (
            self.base_growth_bound * max(0.0, growth_scale)
        )

        # Infeasibility is an expected, handled outcome (starvation), not an
        # error — suppress cobra's warning for it while keeping others.
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore", message="Solver status", category=UserWarning
            )
            solution = self.model.optimize()
        if solution.status != "optimal":
            zeros = {pool: 0.0 for pool in self.uptake_reactions}
            return FBASolution(status=solution.status, growth_rate=0.0, uptake_fluxes=zeros)

        growth = float(solution.objective_value or 0.0)
        fluxes = {
            pool: float(solution.fluxes[reaction_id])
            for pool, reaction_id in self.uptake_reactions.items()
        }
        return FBASolution(status="optimal", growth_rate=growth, uptake_fluxes=fluxes)


def build_minimal_cell_model(
    *,
    nutrient: str = "glc",
    maintenance_atp: float = 1.0,
    mu_max: float = 1.0,
    atp_per_substrate: float = 10.0,
    substrate_per_biomass: float = 4.0,
    atp_per_biomass: float = 20.0,
) -> MetabolicNetwork:
    """Construct a minimal single-carbon metabolic network.

    The caricature network (one carbon/energy source → biomass) is intentionally
    tiny but self-consistent and mass-balanced. Reactions:

    * ``UP_<n>``  : → ``<n>_c``            (uptake; upper bound set per step)
    * ``RESP``    : ``<n>_c`` → k·``atp_c``  (catabolism to energy)
    * ``BIO``     : a·``<n>_c`` + b·``atp_c`` →  (biomass objective, capped at μ_max)
    * ``ATPM``    : ``atp_c`` →              (non-growth maintenance, *fixed*)

    Fixing maintenance (``lb == ub``) prevents the LP from dumping surplus carbon
    into ATP: growth then requires a *determined* uptake, and too little substrate
    to cover maintenance makes the LP infeasible — a clean, emergent starvation
    signal for later modules to interpret as stress/death.

    Args:
        nutrient: Species id of the single carbon/energy source.
        maintenance_atp: Fixed non-growth ATP maintenance (mmol per gDW per hour).
        mu_max: Maximum specific growth rate (per hour), the biomass flux cap.
        atp_per_substrate: ATP yield of catabolising one unit of substrate.
        substrate_per_biomass: Substrate consumed per unit biomass flux.
        atp_per_biomass: ATP consumed per unit biomass flux.

    Returns:
        A ready-to-solve :class:`MetabolicNetwork`.
    """
    import cobra
    from cobra import Metabolite, Model, Reaction

    model = Model("minimal_cell")
    substrate = Metabolite(f"{nutrient}_c", compartment="c")
    atp = Metabolite("atp_c", compartment="c")

    uptake = Reaction(f"UP_{nutrient}")
    uptake.add_metabolites({substrate: 1.0})
    uptake.lower_bound = 0.0
    uptake.upper_bound = 0.0  # set each step from available substrate

    resp = Reaction("RESP")
    resp.add_metabolites({substrate: -1.0, atp: atp_per_substrate})
    resp.lower_bound = 0.0
    resp.upper_bound = 1000.0

    biomass = Reaction("BIO")
    biomass.add_metabolites({substrate: -substrate_per_biomass, atp: -atp_per_biomass})
    biomass.lower_bound = 0.0
    biomass.upper_bound = mu_max

    maintenance = Reaction("ATPM")
    maintenance.add_metabolites({atp: -1.0})
    maintenance.lower_bound = maintenance_atp
    maintenance.upper_bound = maintenance_atp  # fixed maintenance, no dumping

    model.add_reactions([uptake, resp, biomass, maintenance])
    model.objective = "BIO"

    return MetabolicNetwork(
        model,
        biomass_reaction="BIO",
        uptake_reactions={pool_var(nutrient): f"UP_{nutrient}"},
    )


def build_multinutrient_cell_model(
    *,
    carbon: str = "glc",
    nitrogen: str = "nh4",
    maintenance_atp: float = 1.0,
    mu_max: float = 1.0,
    atp_per_carbon: float = 10.0,
    carbon_per_biomass: float = 4.0,
    nitrogen_per_biomass: float = 1.0,
    atp_per_biomass: float = 20.0,
) -> MetabolicNetwork:
    """A two-nutrient network with carbon/nitrogen **co-limitation**.

    Biomass needs both a carbon source (energy + skeleton) and a nitrogen source,
    so growth is limited by whichever is scarcer::

        μ ≤ μ_max,  μ ≤ nitrogen_uptake,  μ ≤ (carbon_uptake − maintenance/10) / 6

    Nitrogen depletion halts growth even with carbon present (the cell goes
    quiescent, still meeting maintenance from carbon); carbon depletion below
    maintenance is infeasible → starvation. Reactions:

    * ``UP_<c>`` / ``UP_<n>`` : uptake (bounds set per step from the pools)
    * ``RESP``  : ``<c>_c`` → k·``atp_c``            (energy from carbon)
    * ``BIO``   : a·``<c>_c`` + b·``<n>_c`` + e·``atp_c`` →  (biomass, capped at μ_max)
    * ``ATPM``  : ``atp_c`` →                        (fixed maintenance)
    """
    import cobra
    from cobra import Metabolite, Model, Reaction

    model = Model("multinutrient_cell")
    c_c = Metabolite(f"{carbon}_c", compartment="c")
    n_c = Metabolite(f"{nitrogen}_c", compartment="c")
    atp = Metabolite("atp_c", compartment="c")

    up_c = Reaction(f"UP_{carbon}")
    up_c.add_metabolites({c_c: 1.0})
    up_c.lower_bound, up_c.upper_bound = 0.0, 0.0

    up_n = Reaction(f"UP_{nitrogen}")
    up_n.add_metabolites({n_c: 1.0})
    up_n.lower_bound, up_n.upper_bound = 0.0, 0.0

    resp = Reaction("RESP")
    resp.add_metabolites({c_c: -1.0, atp: atp_per_carbon})
    resp.lower_bound, resp.upper_bound = 0.0, 1000.0

    biomass = Reaction("BIO")
    biomass.add_metabolites(
        {c_c: -carbon_per_biomass, n_c: -nitrogen_per_biomass, atp: -atp_per_biomass}
    )
    biomass.lower_bound, biomass.upper_bound = 0.0, mu_max

    maintenance = Reaction("ATPM")
    maintenance.add_metabolites({atp: -1.0})
    maintenance.lower_bound = maintenance.upper_bound = maintenance_atp

    model.add_reactions([up_c, up_n, resp, biomass, maintenance])
    model.objective = "BIO"

    return MetabolicNetwork(
        model,
        biomass_reaction="BIO",
        uptake_reactions={
            pool_var(carbon): f"UP_{carbon}",
            pool_var(nitrogen): f"UP_{nitrogen}",
        },
    )
