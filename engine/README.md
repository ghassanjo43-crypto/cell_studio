# vcs-engine — Virtual Cell Studio simulation engine

The **scientific core** of Virtual Cell Studio: a standalone, multi-algorithm
whole-cell simulation kernel. This package has **no web, framework, or database
dependencies** — it is meant to be imported from notebooks, worker processes, and
tests alike. Everything else in the platform (FastAPI backend, React frontend) is a
*client* of this package.

> **Milestones shipped:**
> - **Module 1 — Engine Kernel:** state model, scheduling/reconciliation loop,
>   checkpointing, and a toy module proving the loop end-to-end.
> - **Module 2 — Environment + Transport + FBA metabolism** (`vcs_engine.biology`):
>   the first *emergent growth*. Nutrients flow environment → internal pool →
>   biomass; growth appears and stalls as the medium depletes. Requires the `[fba]`
>   extra (COBRApy).
> - **Module 3 — Gene expression + DNA replication + Division + Death:** the full
>   emergent cell cycle. Stochastic (tau-leaping) gene expression produces an
>   initiator protein that gates DNA replication; a replicated cell above the
>   division mass divides (with binomial molecule partitioning into daughters);
>   starvation drives an emergent death. Lifecycle events stream through the
>   kernel's event log.
> - **Module 4 — Membrane dynamics:** lipid/protein composition and a derived
>   integrity ∈ [0,1] that scales transport (permeability feedback) and, on
>   collapse or osmotic burst, causes emergent lysis death via the death module's
>   membrane hook.
> - **Module 5 — Richer genome + mutation:** heritable genotype factors live in
>   cell state, are realized into phenotype each step through a small gene-regulatory
>   network, and **mutate** on DNA replication. Mutations are non-cosmetic — they
>   scale expression, transport, membrane synthesis, replication speed, or metabolic
>   capacity — and are inherited through division. Lineage/generation are tracked.
> - **Module 10 — Multi-nutrient media + spatial reaction–diffusion:** a two-nutrient
>   (carbon + nitrogen) FBA with **co-limitation**, and a radial diffusion field so a
>   **depletion gradient** forms near the cell. Uptake draws from the surface shell
>   only; growth is limited by the scarcer nutrient or by local depletion.
> - **Module 11 — Internal compartments (organelles):** cytosol / nucleoid / membrane
>   zone, each with an **energy pool**. Metabolism produces energy in the cytosol; it's
>   transported to the nucleoid (expression + replication) and membrane zone (synthesis),
>   which consume it. Transport bottlenecks or metabolic collapse **starve** a
>   compartment → its process throttles → a `compartment_stress` event.
> - **Module 13 — Signalling networks:** a receptor/sensor layer + intracellular signal
>   cascade lets the cell **sense** starvation, nutrient abundance, and membrane stress
>   and **adapt** — under sustained starvation it enters a **survival mode** (scavenge
>   harder, repair the membrane, pause division). Drives the shared phenotype factors,
>   so no other module changes.
>
> Still to come: richer genomes, multicellular / population dynamics.

## Why this design

The platform's hard requirement is that cell behaviour (growth, division, death)
must **emerge** from mechanism — there is never a "grow" button. That forces a
state-driven engine where behaviour is the *output* of integrating biological
processes. Real cells mix processes at different scales and are best described by
*different mathematics* (constraint-based metabolism, stochastic gene expression,
continuous kinetics), so the kernel is deliberately **algorithm-agnostic**:

- **One authoritative `CellState`** — a flat namespace of numeric variables the
  kernel reconciles but does not interpret. Biology-agnostic ⇒ reusable across
  every future cell type.
- **Modules return `StateDelta`s; they never mutate state.** The scheduler
  collects deltas from *all* modules and reconciles them, so modules are
  order-independent and shared-resource contention (e.g. many processes drawing on
  one ATP pool) is expressed naturally as summed increments.
- **Reproducibility is first-class.** Each module gets an independent RNG stream
  derived from `(seed, module-name)`; checkpoints capture every stream's
  bit-generator state, so a restored run continues bit-for-bit.

## Install

```bash
cd engine
python -m pip install -e ".[dev]"
```

## Quick start

```python
from vcs_engine import CellState, Scheduler, ToyModule

state = CellState()
sched = Scheduler(state, seed=20260703)
sched.add_module(ToyModule(production_rate=1.0, decay_rate=0.1, noise_scale=0.4))
sched.initialize()

# Run 200 steps of dt=0.05, recording a trajectory.
trajectory: list[float] = []
sched.run(0.05, 200, observer=lambda s: trajectory.append(s["toy.substance"]))

# Checkpoint (state + RNG bit-state) and resume later, bit-for-bit.
from vcs_engine import save_checkpoint, load_checkpoint
save_checkpoint("run.json", sched.create_checkpoint())
```

## Writing a module

A module is one biological process. It declares which state variables it **owns**
(`provides`) and **reads** (`requires`), sets up its variables in `initialize`, and
returns a `StateDelta` each `step`:

```python
from vcs_engine import Module, CellState, CellStateView, StateDelta

class Decay(Module):
    name = "decay"
    provides = frozenset({"x"})
    requires = frozenset()

    def initialize(self, state: CellState, rng) -> None:
        state.declare_variable("x", 10.0, minimum=0.0)

    def step(self, view: CellStateView, dt: float, rng) -> StateDelta:
        return StateDelta(increments={"x": -0.1 * view["x"] * dt})
```

### Reconciliation rules (deterministic, order-independent)

| Situation | Result |
|---|---|
| Multiple `increments` to one variable | **summed** (shared-resource semantics) |
| Two modules `set` the same variable | error |
| A variable both `set` and `incremented` in one step | error |
| A module writes a key outside its `provides` | error |
| Committed value outside a variable's `[min, max]` | clamped |

### Multi-timescale

Register a module with a stride to run it every _k_ macro-steps with an effective
`dt` covering the interval: `sched.add_module(m, stride=10)`.

## Biology modules (Module 2)

The `vcs_engine.biology` package layers three modules on the kernel to produce
**emergent, nutrient-limited growth**. Install the FBA stack with `pip install -e
".[fba]"` (or `".[dev]"`).

```python
from vcs_engine.biology import build_minimal_cell_scenario
from vcs_engine.biology.naming import MASS, env_var, pool_var

state, sched = build_minimal_cell_scenario(seed=1, glucose_mmol=50.0)
sched.run(0.1, 200)             # 20 h at dt = 0.1 h
print(state[MASS], state[env_var("glc")])   # cell grew; medium depleted
```

### The coupling loop (per step)

```
env.<x> ──uptake──► met.<x> ──FBA──► cell.mass
 (medium)  transport  (internal   metabolism   (biomass)
                       pool)
```

1. **Environment** declares the medium pools `env.<x>` (mmol) and conditions
   (`env.temperature`, `env.pH`); it only *writes* pools if the culture is fed.
2. **Transport** computes a Michaelis–Menten specific uptake rate from each
   nutrient's concentration (`amount / volume`), scales by biomass, and moves that
   amount `env.<x> → met.<x>` (capped at what is present).
3. **Metabolism (FBA)** turns each internal pool into an uptake bound
   `limit = pool / (mass·dt)`, solves the LP to maximise biomass, then grows mass
   by `μ·mass·dt` and decrements pools by what was actually consumed.

`met.<x>` is a **shared pool**: Transport increments it, Metabolism decrements it,
and the kernel sums the two — the reconciliation feature Module 2 is built on.

### Units & scientific assumptions

- Amounts in **mmol**, biomass in **gDW**, time in **hours**; FBA fluxes in
  **mmol·gDW⁻¹·h⁻¹** (field-standard).
- Metabolism is at **quasi-steady state** within a step (FBA balances internal
  metabolites); this is why constraint-based FBA is used rather than kinetic ODEs.
- The built-in `build_minimal_cell_model` is a **caricature** single-carbon network
  (uptake → catabolism → biomass, with *fixed* ATP maintenance). Fixed maintenance
  makes uptake determined (no wasteful carbon dumping) and makes substrate below
  the maintenance requirement **infeasible** — an emergent starvation signal
  (`metabolism.status = "infeasible"`) for later death/division modules to read.
- Default culture is a **closed batch** (no replenishment): the medium can only
  deplete, so growth is self-limiting.

## Cell lifecycle (Module 3)

Layered on Module 2, four modules produce an **emergent cell cycle** — no `divide`
or `grow` command exists anywhere.

```python
from vcs_engine.biology import build_lifecycle_scenario, MASS, DIVISIONS, LIFECYCLE_STATUS

state, sched = build_lifecycle_scenario(seed=1, glucose_mmol=40.0)
sched.run(0.1, 400)
print(state[DIVISIONS], state.metadata[LIFECYCLE_STATUS])   # e.g. 2  DEAD
for e in state.events:                                       # lifecycle event stream
    print(e.step, e.type, dict(e.data))
```

- **Gene expression** (`GeneExpressionModule`) — **stochastic tau-leaping**: per
  gene, per step, transcription/translation/decay firings are Poisson draws with
  mean `propensity·dt`, using the module's own reproducible RNG stream. Rates scale
  with mass. One gene is the **replication initiator**; its protein crossing a
  threshold sets `dna.initiator_ready` and emits a `gene_activated` event.
- **DNA replication** (`DnaReplicationModule`) — a gated 0→1 progress process.
  Initiates only when `mass ≥ initiation_mass` **and** the initiator is ready;
  advances by `dt/replication_time`; sets `dna.replication_complete` at 1.
- **Division** (`DivisionModule`) — fires only when *alive*, *replication complete*,
  and *mass ≥ division_mass*. Continuous quantities (mass, pools) split by a fixed
  fraction; molecule counts split by **binomial partitioning** (the correct
  stochastic partitioning-noise model). The daughter's state is recorded in the
  `division` event; DNA state is reset for the next cycle.
- **Death** (`DeathModule`) — classifies `lifecycle.status`
  (`GROWING → STRESSED → DYING → DEAD`) from a consecutive-starvation counter
  (metabolism reporting non-`optimal`), or kills immediately on biomass loss or a
  future membrane-integrity hook. On death it sets `cell.alive = 0`, which makes
  every other module no-op, and emits a `death` event.

**Emergent cycle:** nutrients → growth + gene expression → initiator protein →
replication → division (repeats) → medium depletes → starvation → death.

### Lifecycle events

Discrete occurrences are recorded as `Event(type, time, step, data)` on
`state.events` (checkpointed). Types: `gene_activated`, `replication_start`,
`replication_complete`, `division`, `death`, `membrane_rupture`, `mutation`. Unlike
single-writer metadata, **many modules can emit events in one step** — the scheduler
concatenates them.

## Genome, regulation & mutation (Module 5)

`build_evolution_scenario` adds a `GenomeModule` on top of the full lifecycle,
making the cell's *parameters themselves* evolvable state.

```python
from vcs_engine.biology import build_evolution_scenario, geno_var, GENERATION, LINEAGE_ID

state, sched = build_evolution_scenario(seed=3, glucose_mmol=60.0, mutation_rate=1.5)
sched.run(0.1, 500)
print(state[GENERATION], state.metadata[LINEAGE_ID])          # 2  "0.0.0"
print(state[geno_var("metabolism")])                          # e.g. 0.899 (mutated)
[e for e in state.events if e.type == "mutation"]             # mutation history
```

- **Genotype** (`geno.<target>`, `geno.expr.<gene>`) — heritable multiplicative
  factors, all starting at 1.0. Stored in cell state (so they checkpoint and are
  inherited), **not split** at division (intensive traits), clamped to `[0.1, 10]`.
- **Phenotype** (`pheno.<target>`) — realized each step as `genotype × regulation`,
  where a small **gene-regulatory network** lets a regulator gene's protein Hill-
  activate/repress its target. Modules read `pheno.*`/`geno.expr.*` via
  `view.get(..., 1.0)`, so behavior is unchanged when no genome is present
  (backward-compatible with Modules 2–4).
- **Mutation** — on each completed replication, `Poisson(mutation_rate)` mutations
  each perturb one random genotype factor by a log-normal multiplier (using the
  module's checkpointed RNG stream) and emit a `mutation` event. Mutations are
  **not cosmetic**: they scale expression rate, transport efficiency, membrane
  synthesis, replication speed, or metabolic capacity — directly changing behavior
  and fitness. They persist through division (heritable).
- **Lineage** — `cell.generation` counts ancestral divisions and a `lineage.id`
  path (e.g. `"0.0.0"`) tracks the followed cell; each `division` event names both
  daughter lineages and records the inherited genotype for the sister.

## Membrane dynamics (Module 4)

`MembraneModule` gives the cell an envelope with **composition** (`membrane.lipid`,
`membrane.protein`) and a derived **integrity** ∈ [0,1]:

- **Sizing:** required surface area scales as `area_coefficient · mass^(2/3)`
  (surface ∝ volume^(2/3), volume ∝ mass). Material is synthesised toward that area,
  drawing a small amount of substrate from the shared internal pool (`met.<x>`) —
  coupling membrane maintenance to metabolism — capped by a max rate, and turned
  over by first-order decay.
- **Permeability feedback:** `TransportModule` multiplies uptake by
  `membrane.integrity`, so a lagging or degraded membrane slows growth (negative
  feedback). Defaults to 1.0 when no membrane module is present.
- **Lysis death:** when the membrane cannot cover the cell (coverage collapse) or
  osmotic load bursts it, integrity is driven to 0 and a `membrane_rupture` event is
  emitted; `DeathModule`'s `membrane_integrity_getter` hook then records a death with
  cause `membrane_integrity`. This is a death pathway independent of metabolic
  starvation.

In a healthy `build_lifecycle_scenario` run the membrane keeps integrity high while
growing (it never ruptures), and division splits membrane material into the
daughters. Rupture is a capability exercised directly in the tests (starvation of
membrane substrate, or a lowered osmotic-burst ratio).

## Multi-nutrient media & spatial reaction–diffusion (Module 10)

`build_spatial_scenario` places the cell at the centre of a radial diffusion field
of **two** nutrients (carbon `glc`, nitrogen `nh4`), running the full lifecycle on top.

```python
from vcs_engine.biology import build_spatial_scenario, field_var, LIMITING_KEY

state, sched = build_spatial_scenario(seed=1, glucose_conc=25.0, ammonium_conc=6.0, n_shells=6)
sched.run(0.1, 300)
print([round(state[field_var("glc", i)], 2) for i in range(6)])   # surface → bulk gradient
print(state.metadata[LIMITING_KEY])                                # met.glc | met.nh4 | ""
```

- **Multi-nutrient FBA** (`build_multinutrient_cell_model`) — biomass needs both a
  carbon and a nitrogen source, so growth is co-limited:
  `μ ≤ μ_max`, `μ ≤ nitrogen_uptake`, `μ ≤ (carbon_uptake − maintenance/10)/6`.
  Nitrogen depletion halts growth even with carbon present (quiescence, still meeting
  maintenance); carbon below maintenance is infeasible → starvation. Metabolism records
  the **limiting** nutrient (`metabolism.limiting`) and, in the spatial scenario, emits
  `nutrient_limited` events on change.
- **Reaction–diffusion** (`DiffusionModule`) — the extracellular space is a stack of
  radial shells (`field.<n>.<i>`, shell 0 = cell surface). An explicit finite-difference
  Laplacian with reflective boundaries moves nutrient between shells — a closed,
  **conserved** field. Stable for `diffusion_alpha < 0.5`. Deterministic, so it
  checkpoints like the rest of the cell.
- **Surface uptake** (`SpatialTransportModule`) — the cell takes up nutrient from the
  **surface shell only**, using the *local* concentration for Michaelis–Menten kinetics.
  When uptake outpaces diffusive resupply, a depletion zone forms and the surface
  concentration falls — an emergent **spatial nutrient limitation** distinct from bulk
  depletion. Uptake still scales with membrane integrity and the transport genotype.

All existing single-nutrient scenarios are unchanged (the limitation events are opt-in).

## Internal compartments & the energy economy (Module 11)

`build_compartment_scenario` gives the cell three internal compartments, each with an
**energy pool**, and runs the full lifecycle on top.

```python
from vcs_engine.biology import build_compartment_scenario, energy_var, CYTOSOL, NUCLEOID

state, sched = build_compartment_scenario(seed=1, glucose_mmol=40.0, transport_rate=0.5)
sched.run(0.1, 300)
print(state[energy_var(CYTOSOL)], state[energy_var(NUCLEOID)])
[e for e in state.events if e.type == "compartment_stress"]
```

- **Compartments:** `cytosol` (metabolism produces energy from growth flux),
  `nucleoid` (gene expression + DNA replication consume it), `membrane_zone` (membrane
  synthesis consumes it). Each has an `energy.<compartment>` pool.
- **Energy transport** (`CompartmentModule`): Fickian transfer moves energy from the
  cytosol to the consumers at a limited `transport_rate`, and every compartment leaks
  energy (first-order), so each depends on continuous supply. A gradient forms across
  compartments under load.
- **Throttling + stress:** each consumer process scales its rate by energy availability
  `e / (e + K)` and consumes energy per unit work. When a compartment runs low
  (transport can't keep up, or metabolism stalls and production stops), its process
  slows and a `compartment_stress` event fires — a new failure pathway that reinforces
  death when metabolism collapses.

This is **opt-in** (a process couples only when given an `energy_var`), and the energy
throttle scales rates without changing the RNG call sequence, so every existing scenario
reproduces bit-for-bit.

## Signalling networks & adaptive response (Module 13)

`build_signalling_scenario` gives the cell a **receptor/sensor layer** and a small
signalling cascade so it senses its state and adapts.

```python
from vcs_engine.biology import build_signalling_scenario, SIGNAL_STARVATION, SIGNAL_MODE

state, sched = build_signalling_scenario(seed=1, glucose_mmol=40.0)
sched.run(0.1, 300)
print(state[SIGNAL_STARVATION], state.metadata[SIGNAL_MODE])   # e.g. 1.0  SURVIVAL
[e for e in state.events if e.type == "survival_mode_entered"]
```

- **Sensors** (each step): metabolic starvation (`metabolism.status ≠ optimal`), nutrient
  abundance (internal pool, Michaelis), and membrane stress (integrity below a threshold).
- **Signals** (`signal.starvation` / `signal.growth` / `signal.membrane_stress`, each in
  [0, 1]): first-order integrators of the sensors, so the cell responds to *sustained*
  conditions (a cascade with memory), not transient blips.
- **Adaptive responses:** `SignallingModule` drives the shared phenotype factors —
  `pheno.transport` ↑ (scavenge harder), `pheno.membrane` ↑ (repair), `pheno.replication`
  ↓ (pause division) — and sets `signalling.mode` (`NORMAL` / `GROWTH` / `SURVIVAL`) with
  `survival_mode_entered` / `survival_mode_exited` events. Because transport, membrane, and
  replication already read those factors, **no existing module is modified**; signalling
  simply owns the phenotype layer (used *instead of* the genome module, which also owns it).

Deterministic (no RNG) → reproducible and checkpointable; existing scenarios are untouched.

## Population dynamics — colonies & selection (Module 15)

`vcs_engine.population` sits **above** the single-cell engine: it runs many cells at
once, competing in one shared medium, so colonies, lineage trees, and population-level
evolution emerge. It adds **no new biology** — each cell is a full
`build_evolution_scenario` with its own reproducible RNG streams.

```python
from vcs_engine.population import Population, PopulationConfig

pop = Population(PopulationConfig(seed=2, medium_glucose=200.0,
                                  initiation_mass=0.6, division_mass=1.0))
for _ in range(300):
    pop.step(0.1)
s = pop.summary()
print(s["alive"], s["born"], s["died"], s["dominant_lineage"])   # colony state
[e for e in pop.events if e["type"] == "clone_expansion"]
```

- **Shared medium & competition.** Each tick the remaining glucose is broadcast into
  every cell's `env.glc`; the amount a cell takes up is subtracted before the next cell
  steps. This sequential draw makes cells **compete** (scarce glucose starves the cells
  processed later) and conserves mass exactly.
- **Real daughter cells.** A cell's `division` event already records the sister
  daughter's partitioned biomass/pools and inherited genotype — the population turns that
  record into a **new cell** with a fresh, deterministically-derived seed.
- **Lineage & selection.** Each cell keeps a nested `lineage_id` (e.g. `0.1.0`) and a
  clone `root`; genotypes mutate at replication and are inherited, so fitter clones divide
  more and expand while others go extinct — evolution at the population level.
- **Events:** `cell_birth`, `cell_death`, `clone_expansion`, `population_extinct`.
- **Determinism:** founder/daughter seeds come from `(seed, serial)` and the competition
  order is the stable birth order, so a whole colony run is bit-for-bit reproducible and
  `create_checkpoint` / `restore_checkpoint` continues it exactly.

## Digital Petri Dish — a spatial lab culture (Module 16)

`vcs_engine.petri` is a **vectorised, agent-based spatial model** — a *new capability*
built on the engine's ideas (the 2D analogue of `biology.spatial`'s reaction–diffusion
and the same heritable-genotype/mutation concept), not a rewrite. Thousands of
lightweight cell agents live on a grid, so colony expansion, biofilm fronts, nutrient-
limited cores, clone competition, founder effects, and colony extinction all emerge —
and it stays fast (an 80×80 dish steps thousands of cells in well under a millisecond).

```python
from vcs_engine.petri import PetriDish, PetriConfig

dish = PetriDish(PetriConfig(seed=1, width=80, height=80, initial_cells=8,
                             nutrient_pattern="gradient"))
for _ in range(150):
    dish.step(0.1)
s = dish.summary()
print(s["alive"], s["colonies"], s["dominant_clone"], s["occupancy"])
[e for e in dish.events if e["type"] == "clone_dominant"]
```

- **Grid state:** a `nutrient` field diffuses each tick (2D explicit Laplacian, zero-flux
  boundaries); an `occupant` grid holds one cell per site — which is what makes
  competition **local** and gives colonies **fronts** (only edge cells find an empty
  neighbour to divide into; packed interiors stop dividing and deplete their nutrient).
- **Per-tick, vectorised over living cells:** diffuse → sense local nutrient + neighbour
  density (a quorum-like signal that raises maintenance = contact inhibition) → uptake
  (Michaelis–Menten × transport genotype, capped by the site) → grow on the surplus →
  starve/die in depleted cores → divide into an empty neighbour, **mutating the daughter's
  genotype**. Founder clones compete for space + nutrient; fitter clones dominate, weaker
  colonies go extinct, and a closed dish eventually crashes (a fed one forms a biofilm).
- **Environmental heterogeneity:** `nutrient_pattern` ∈ `uniform` / `gradient` / `patches`.
- **Readouts:** `summary()` returns population stats **plus coarse heat maps** (population
  density, nutrient, mutation load, ATP/energy), a dominant-clone map (lineage view), and a
  capped sample of cell positions for rendering. **Events:** `colony_founded`,
  `colony_extinct`, `clone_dominant`, `biofilm_confluent`, `population_extinct`.
- **Determinism:** a single seeded `numpy` generator drives mutation, division order, and
  placement → bit-for-bit reproducible, and `create_checkpoint` / `restore_checkpoint`
  continues a dish exactly (grid + agent arrays + RNG state).

## Architecture

```
vcs_engine/
├── state/
│   ├── cell_state.py     # CellState (truth) + CellStateView (read-only) + event log
│   ├── delta.py          # StateDelta (increments / sets / metadata / events)
│   ├── events.py         # Event (discrete, timestamped lifecycle record)
│   └── serialization.py  # state + checkpoint (de)serialization (JSON)
├── kernel/
│   ├── module.py         # Module contract: initialize / step / provides / requires
│   └── scheduler.py      # step loop, RNG streams, reconciliation, events, checkpoints
├── modules/
│   └── toy.py            # trivial mean-reverting + noise module (kernel smoke test)
└── biology/              # Modules 2 & 3 (needs cobra; import-lazy)
    ├── naming.py         # env.<x> / met.<x> / cell.mass / dna.* / mrna.* variable names
    ├── config.py         # NutrientSpec, EnvironmentConfig
    ├── genome.py         # GeneSpec, GenomeConfig
    ├── environment.py    # EnvironmentModule (declares/replenishes medium)
    ├── transport.py      # TransportModule (Michaelis-Menten uptake)
    ├── fba.py            # MetabolicNetwork + minimal cell model (COBRApy)
    ├── metabolism.py     # MetabolismFBAModule (FBA -> growth + consumption)
    ├── expression.py     # GeneExpressionModule (stochastic tau-leaping)
    ├── replication.py    # DnaReplicationModule (gated progress)
    ├── division.py       # DivisionModule (autonomous split + partitioning)
    ├── death.py          # DeathModule (status classification + emergent death)
    ├── membrane.py       # MembraneModule (composition, integrity, permeability, lysis)
    ├── genotype.py       # GenomeModule (heritable genotype, regulation, mutation)
    ├── spatial.py        # DiffusionModule + SpatialTransportModule (reaction–diffusion)
    ├── compartments.py   # CompartmentModule (organelle energy pools + transport + stress)
    ├── signalling.py     # SignallingModule (sensors → signal cascade → adaptive phenotype)
    └── scenario.py       # build_minimal / _lifecycle / _evolution / _spatial / _compartment / _signalling
```

## Tests & type checks

```bash
cd engine
python -m pytest            # unit + golden-trajectory + checkpoint reproducibility
python -m mypy              # strict type checking (config in pyproject.toml)
```

The **golden-trajectory** test (`tests/test_golden_trajectory.py`) pins a
`(seed, config)` to a stored trajectory and fails on any numerical drift. Regenerate
it intentionally with `python -m tests.generate_golden`.
