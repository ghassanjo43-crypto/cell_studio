# Virtual Cell Studio (VCS) — System Architecture

**Status:** Draft for approval (Step 1)
**Author:** Lead Architecture (acting: SW Architect / Computational Biologist / Scientific AI Engineer / UX / Full-Stack)
**Date:** 2026-07-03

> This document is the architectural blueprint. **No application modules are built until this is approved.**
> After approval we implement one module at a time, each with clean architecture, docs, tests, and production quality.

---

## 0. The one hard problem that shapes everything

Every other decision follows from a single requirement:

> **Growth, division, mutation, and death must _emerge_ from an internal biological model. There is never a "Grow Cell" button. The user changes only initial conditions and environment.**

This forbids a scripted/animation architecture. It demands a **mechanistic, state-driven simulation engine** where cell behavior is the *output* of numerically integrating biological processes, and the 3D scene is merely a *view* of that state.

That single constraint drives four load-bearing decisions:

| Decision | Why |
|---|---|
| **Simulation engine is a standalone Python package**, independent of the web/API layer | It must be testable, runnable in notebooks and worker processes, and never coupled to a request/response cycle. It is the scientific core; the web app is a client of it. |
| **Multi-scale, multi-algorithm "whole-cell" kernel** (not one big ODE) | Real cells mix processes at wildly different scales — genome-scale metabolism (best solved as constraint-based/FBA), stochastic low-copy gene expression (best solved with Gillespie SSA), and bulk kinetics (ODE). No single solver fits all. We partition the cell into modules, each with the *right* math, coupled through shared state. This mirrors the Karr et al. 2012 *M. genitalium* whole-cell model and E-Cell/VCell lineage. |
| **Simulation runs as an asynchronous, checkpointable service** that streams state frames | Simulations are long-running and CPU-bound. They cannot live in an HTTP handler. A worker runs the engine and streams frames over WebSocket; results are persisted for replay. |
| **3D/VR is a rendering _projection_ of simulation state**, with its own mapping layer | We can never render every molecule. The renderer consumes a compact "visualization state" derived from the true state via a mapping/aggregation layer, using instancing + LOD. |

---

## 1. Design principles

1. **Mechanism over animation.** Behavior emerges from equations, not keyframes.
2. **Separation of the scientific core from delivery.** The engine knows nothing about HTTP, React, or Postgres.
3. **Reproducibility is a feature, not an afterthought.** Seeded RNG, versioned models, immutable run provenance. A published result must be re-runnable bit-for-bit.
4. **Stand on the shoulders of computational biology.** Interoperate with community standards (SBML, BiGG, KEGG/MetaCyc, SBO) and proven libraries (COBRApy, libRoadRunner/Tellurium) rather than reinventing solvers.
5. **AI is an advisor and translator, never a silent source of truth.** LLM output is always validated against schemas and grounded in references before it touches simulation state.
6. **Everything is a plugin.** Cell types (minimal, cancer, immune, stem…) and biological modules register into the kernel. New biology is added, not forked.
7. **Progressive fidelity.** The same architecture supports a fast coarse model (real-time, interactive) and a slow high-fidelity model (batch, publication) via swappable module implementations.

---

## 2. High-level system architecture

```
                          ┌───────────────────────────────────────────────┐
                          │                   CLIENT (Browser / XR)         │
                          │  React + TS + Vite                              │
                          │  ┌───────────────┐   ┌────────────────────────┐ │
                          │  │ Design Studio │   │  3D Viewport (R3F)      │ │
                          │  │ (genome, mem, │   │  Three.js / WebXR       │ │
                          │  │  metabolism,  │   │  instanced + LOD        │ │
                          │  │  environment) │   └────────────────────────┘ │
                          │  └───────────────┘   ┌────────────────────────┐ │
                          │  ┌───────────────┐   │  Analytics panels      │ │
                          │  │  AI Copilot   │   │  (charts, time series) │ │
                          │  └───────────────┘   └────────────────────────┘ │
                          └───────────┬──────────────────────┬──────────────┘
                            REST (config, CRUD)      WebSocket (live frames)
                                      │                      │
                          ┌───────────▼──────────────────────▼──────────────┐
                          │                 API GATEWAY (FastAPI)            │
                          │  Auth (JWT) · Validation (Pydantic) · Routing    │
                          │  Simulation control API · AI orchestration API   │
                          └───┬───────────────┬───────────────┬─────────────┘
                              │               │               │
                 ┌────────────▼───┐   ┌───────▼────────┐  ┌───▼──────────────┐
                 │  Sim Control   │   │  AI Service    │  │  Persistence     │
                 │  Service       │   │  (Claude /     │  │  Layer           │
                 │  (dispatch,    │   │   OpenAI,      │  │  Postgres +      │
                 │   checkpoint,  │   │   tool-use,    │  │  object store    │
                 │   stream)      │   │   RAG)         │  │  (trajectories)  │
                 └───────┬────────┘   └────────────────┘  └──────────────────┘
                         │ job dispatch + frame stream (message broker)
                 ┌───────▼───────────────────────────────────────────────────┐
                 │             SIMULATION WORKER(S)  (Python process pool)     │
                 │  ┌───────────────────────────────────────────────────────┐ │
                 │  │            SIMULATION ENGINE (pure Python pkg)          │ │
                 │  │   Kernel · Scheduler · Shared State · Module Registry   │ │
                 │  │   Metabolism(FBA) · GeneExpression(SSA) · Transport     │ │
                 │  │   Membrane · Replication/Repair · Division · Environment│ │
                 │  └───────────────────────────────────────────────────────┘ │
                 └─────────────────────────────────────────────────────────────┘
```

**Why a worker tier separate from the API:** simulations are long-running and CPU-bound (NumPy/SciPy/LP solves). Putting them behind a broker (Redis/RabbitMQ, or Postgres-backed queue at MVP) keeps the API responsive, lets simulations survive client disconnects, enables horizontal scaling of compute independently of web traffic, and gives us natural checkpoint/resume boundaries.

---

## 3. Simulation engine architecture (the scientific core)

This is the crown jewel and is designed to be usable **without any of the web stack**.

### 3.1 The kernel: shared-state, multi-algorithm time stepping

The cell state lives in a single authoritative **CellState** (metabolite pools, molecule counts, energy currency, DNA/RNA/protein inventories, membrane composition, geometry, environment). The kernel advances simulated time in steps. On each step the **Scheduler** invokes every registered **Module**; each module reads the shared state, computes its contribution over `dt`, and returns a **delta**. The kernel reconciles deltas (resolving shared-resource contention, e.g. ATP consumed by many processes) and commits the new state.

```
Module interface (every biological process implements this):

    class Module(Protocol):
        name: str
        provides: set[str]      # state variables it can change
        requires: set[str]      # state variables it reads
        def initialize(self, state: CellState, params: ModuleParams) -> None: ...
        def step(self, state: CellStateView, dt: float, rng: Generator) -> StateDelta: ...
```

**Why deltas + reconciliation instead of direct mutation:** it makes the coupling explicit, keeps modules order-independent within a step, allows shared-resource arbitration (the whole-cell modeling insight), and makes each module independently unit-testable with a fixed input state.

### 3.2 Multi-algorithm submodels (right math per process)

| Submodel | Method | Rationale |
|---|---|---|
| **Metabolism** | Flux Balance Analysis (constraint-based LP) via COBRApy | Genome-scale, parameter-light, steady-state fluxes; the standard for "does the cell have a feasible way to make biomass from these nutrients?" |
| **Gene expression / regulation** | Stochastic (Gillespie SSA / tau-leaping) for low-copy species; ODE for bulk | Transcription/translation of few-copy molecules is inherently noisy — noise drives phenotypic variability, mutation outcomes, and death. Determinism would be biologically wrong. |
| **Enzyme kinetics / signaling** | ODE (Michaelis–Menten, mass action) via SciPy / libRoadRunner | Continuous, well-mixed, high-copy dynamics. |
| **Transport & membrane** | Kinetic flux terms (passive diffusion, active/ATP-coupled) | Couples environment ↔ cytoplasm; gates nutrient uptake and waste export. |
| **DNA replication & repair** | Discrete-event process model | Replication is a threshold/progress process; mutations arise from repair error rates (RNG-driven). |
| **Growth & division** | Mass/volume accumulation with division trigger | **This is where "growth" emerges** — biomass accumulates from metabolic flux; when volume/mass crosses a checkpoint and DNA is replicated, division fires. No button. |
| **Environment** | Well-mixed pools (MVP) → reaction-diffusion PDE (later) | Nutrient depletion and waste accumulation feed back into fitness. |

**Why hybrid instead of one ODE system:** a single stiff ODE cannot capture stochastic low-copy gene expression, and a genome-scale kinetic model would need thousands of unmeasured parameters. The hybrid keeps each process in its most defensible, most parameter-efficient formalism.

### 3.3 Time-scale coupling

Processes run at different cadences (fast kinetics vs. slow division). The scheduler supports **per-module step multipliers** and a **fixed macro-step** at which shared state synchronizes. FBA is re-solved when uptake bounds change materially; SSA advances event-by-event within a macro-step. This is the classic multi-scale orchestration pattern.

### 3.4 Emergent outcomes (what the engine reports, never scripts)

`GROWING · DIVIDED · QUIESCENT · MUTATED · STRESSED · DYING · DEAD` — each is a **derived classification of state** (e.g. `DEAD` = ATP below maintenance threshold for N steps, or membrane integrity lost), not an authored event.

### 3.5 Reproducibility & provenance (first-class)

- Single seeded `numpy.random.Generator`, seed stored on the run.
- Every run pins a **model version** (module set + parameter set + solver versions).
- State is **checkpointable** (serialize `CellState` + RNG bit-state) → pause/resume/fork.
- Full provenance record: config hash, seed, engine version, environment. A result can be reproduced exactly.

### 3.6 Scientific interoperability

- **SBML** for model import/export (kinetic submodels), **SBO** for term semantics.
- **BiGG / KEGG / MetaCyc** identifiers for metabolites, reactions, genes.
- Genome config accepts standard sequence formats (FASTA/GenBank) for future genome-driven models.

*Why:* credibility and reuse. A platform that speaks community standards can import existing published models and export ours for peer validation, instead of being a closed toy.

---

## 4. Backend services (FastAPI)

Thin, stateless API tier; all heavy work delegated.

- **Auth Service** — JWT issue/verify, refresh, RBAC (owner/collaborator/viewer on projects).
- **Design Service** — CRUD for cell designs (genome, membrane, metabolism, environment presets). Validates against Pydantic schemas that mirror the engine's config models (single source of truth for schemas).
- **Simulation Control Service** — create run → enqueue job → track lifecycle (`QUEUED/RUNNING/PAUSED/DONE/FAILED`) → stream frames via WebSocket → checkpoint/fork/cancel.
- **AI Orchestration Service** — see §5.
- **Persistence Layer** — repositories over Postgres + object store.

**Why thin API + workers:** protects request latency, isolates failure domains, and lets simulation compute scale on its own axis.

---

## 5. AI architecture

AI is an **advisory/translation layer**. It never writes simulation state directly.

**Capabilities**
1. **NL → validated design.** "Design a minimal cell that survives on glucose at 37 °C" → structured config. Implemented with **tool-use / function-calling**: the model must emit arguments conforming to our Pydantic design schema; anything invalid is rejected and repaired, never blindly applied.
2. **Result interpretation & hypothesis generation.** "Why did the cell die at t=4200s?" → the AI is given the *trajectory summary and provenance*, and explains using grounded biological knowledge.
3. **Parameter/experiment suggestion.** Proposes next environmental conditions to test a hypothesis.
4. **Knowledge grounding (RAG).** Retrieval over a curated biology corpus (pathway DBs, references) so explanations cite sources rather than hallucinate.

**Model strategy**
- Default to the latest, most capable Claude models via the Anthropic SDK, with OpenAI as an alternate provider behind a **provider-abstraction interface** (so we are not locked in).
  - Reasoning-heavy design/hypothesis: **Claude Opus 4.8**.
  - Interactive copilot / lower latency: **Claude Sonnet 5**.
  - Cheap/fast classification & routing: **Claude Haiku 4.5**.
- All prompts, tool schemas, and model IDs live in one `ai/` config module; no model IDs scattered in code.

**Guardrails**
- Structured output validation (Pydantic) on every AI-produced artifact.
- The AI proposes; the engine and validators dispose. A biologically infeasible design is caught by the engine (FBA infeasibility), not asserted true by the LLM.

*Why this shape:* in a scientific tool, an ungrounded/unvalidated LLM is a liability. Function-calling + schema validation + RAG turns the LLM into a safe accelerator.

---

## 6. 3D rendering architecture (React Three Fiber / Three.js)

**Core principle:** the renderer is a **projection of simulation state**, not a parallel simulation.

```
CellState (truth)  ──►  Visualization Mapper  ──►  VizState (compact)  ──►  R3F scene graph
 (millions of                (aggregate,            (instanced pools,        (declarative,
  molecules,                  sample, LOD-select)    fields, geometry)         XR-agnostic)
  fields)
```

- **Visualization Mapper** turns true state into a bounded, renderable representation: statistical/representative molecule populations, concentration fields, membrane geometry, organelle proxies. We render *representatives*, not every molecule.
- **Instanced rendering** (`InstancedMesh`) for large populations; **LOD** to swap detail by camera distance; GPU shaders for concentration fields.
- **Decoupled cadence:** simulation frames arrive at the sim's pace; the renderer interpolates at display refresh. Sim time ≠ frame time.
- **Declarative scene graph** in R3F so the same graph is reused across desktop and XR.

*Why a mapping layer:* it is the only way to keep rendering tractable and to let visualization fidelity scale independently from simulation fidelity.

---

## 7. Future VR architecture (WebXR)

The 3D layer is designed XR-ready from day one so VR is **additive, not a rewrite**:

- **`@react-three/xr` / WebXR** — the existing R3F scene graph renders to an XR session unchanged.
- **Input/camera abstraction** — a `CameraController` / `InteractionController` indirection so mouse/orbit and XR controllers/hands are interchangeable.
- **Same state stream** — VR consumes the identical VizState stream; no engine changes.
- **Comfort & performance budgets** — foveation, aggressive LOD, and instancing become mandatory (already built).

*Why now (in design):* retrofitting XR onto a camera-coupled renderer is expensive; abstracting input/camera up front is nearly free.

---

## 8. Database schema (PostgreSQL)

**Strategy:** relational metadata in Postgres (JSONB for flexible biological config); **bulk time-series trajectory data in object storage / columnar files (Parquet)**, referenced from Postgres. Trajectories are large, append-only, and read in bulk — a row-per-timestep-per-species table would not scale.

```
users(id, email, password_hash, created_at, ...)

projects(id, owner_id → users, name, description, created_at)

project_members(project_id → projects, user_id → users, role)      -- RBAC

cell_designs(id, project_id → projects, name,
             genome        JSONB,        -- genes, sequences, regulation
             membrane      JSONB,        -- lipid/protein composition
             metabolism    JSONB,        -- pathway/reaction selection
             base_cell_type TEXT,        -- minimal | cancer | immune | ...
             created_at, updated_at)

environments(id, project_id → projects, name,
             nutrients JSONB, energy_sources JSONB,
             temperature REAL, ph REAL, other JSONB)

model_versions(id, name, module_set JSONB, param_set JSONB,
               engine_version TEXT, created_at)   -- reproducibility anchor

simulations(id, project_id → projects, design_id → cell_designs,
            environment_id → environments, model_version_id → model_versions,
            status TEXT, seed BIGINT, config_hash TEXT,
            started_at, ended_at, outcome TEXT,      -- DEAD/DIVIDED/...
            created_by → users)

simulation_checkpoints(id, simulation_id → simulations,
                        sim_time REAL, state_blob_uri TEXT,  -- object store
                        rng_state BYTEA, created_at)         -- pause/resume/fork

trajectory_index(id, simulation_id → simulations,
                 t_start REAL, t_end REAL, storage_uri TEXT, -- Parquet in object store
                 schema JSONB)

events(id, simulation_id → simulations, sim_time REAL,
       type TEXT, payload JSONB)      -- division, mutation, death, stress

ai_conversations(id, project_id → projects, user_id → users, created_at)
ai_messages(id, conversation_id → ai_conversations, role TEXT,
            content JSONB, tool_calls JSONB, model_id TEXT, created_at)
```

*Why JSONB for biology config:* genome/membrane/metabolism structures evolve rapidly and vary by cell type; rigid columns would fight the science. JSONB gives flexibility with indexable querying. Numeric relationships and access control stay relational.

---

## 9. Repository / folder structure (monorepo)

**Why a monorepo:** the engine, backend, and frontend share schemas and must version together; a monorepo keeps schema/type generation and CI coherent.

```
cell_studio/
├── docs/                     # architecture, ADRs, module specs, scientific refs
│   └── ARCHITECTURE.md
│
├── engine/                   # ⭐ standalone Python scientific core (no web deps)
│   ├── vcs_engine/
│   │   ├── kernel/           # scheduler, shared state, delta reconciliation
│   │   ├── state/            # CellState, serialization, checkpointing
│   │   ├── modules/          # metabolism, gene_expression, transport,
│   │   │                     #   membrane, replication, division, environment
│   │   ├── celltypes/        # registry: minimal, cancer, immune, stem...
│   │   ├── solvers/          # FBA (COBRApy), SSA, ODE (SciPy/roadrunner) wrappers
│   │   ├── io/               # SBML, FASTA/GenBank, BiGG/KEGG adapters
│   │   └── provenance/       # seeds, versioning, run records
│   ├── tests/                # unit + property + regression (golden trajectories)
│   └── pyproject.toml
│
├── backend/                  # FastAPI delivery tier
│   ├── app/
│   │   ├── api/              # routers: auth, designs, simulations, ai
│   │   ├── services/         # sim control, ai orchestration
│   │   ├── schemas/          # Pydantic (single source of truth for API+engine config)
│   │   ├── repositories/     # Postgres + object store access
│   │   ├── workers/          # simulation worker entrypoints
│   │   └── core/             # config, security (JWT), db, broker
│   ├── tests/
│   └── pyproject.toml
│
├── ai/                       # provider-agnostic AI layer (imported by backend)
│   ├── providers/            # claude, openai adapters
│   ├── tools/                # function-calling schemas (NL → design)
│   ├── rag/                  # retrieval over biology corpus
│   └── prompts/
│
├── frontend/                 # React + TS + Vite + R3F
│   ├── src/
│   │   ├── features/         # design-studio, viewport, analytics, ai-copilot
│   │   ├── three/            # scene graph, viz mapper, instancing, LOD, xr/
│   │   ├── api/              # REST + WebSocket clients
│   │   ├── state/            # app state
│   │   └── types/            # generated from backend OpenAPI/schemas
│   └── package.json
│
├── shared/                   # cross-cutting schema/type generation
│   └── schema-gen/           # Pydantic → TS types, OpenAPI
│
├── infra/                    # Render (dev) → AWS/GCP; IaC, CI/CD, docker
└── scripts/
```

**Key structural decision — `engine/` is a pure package with its own `pyproject.toml`:** it can be `pip install`ed, unit-tested, and driven from Jupyter with zero web dependencies. The backend imports it; the worker runs it. This is what keeps the science reusable and honest.

---

## 10. End-to-end data flow (one simulation)

1. User configures cell + environment in the **Design Studio** (optionally via **AI Copilot**, which emits a schema-validated config).
2. Frontend `POST`s the design/environment → **Design Service** validates (Pydantic) and persists.
3. User starts a run → **Simulation Control Service** creates a `simulations` row (with seed, config hash, pinned model version) and enqueues a job on the broker.
4. A **Simulation Worker** loads the `engine`, builds `CellState`, and runs the kernel loop. Growth/division/death **emerge**.
5. The worker emits **frames** (compact VizState + metrics + events) → streamed to the client over **WebSocket**; full trajectory written to object store (Parquet), events/checkpoints to Postgres.
6. Frontend **Viz Mapper** renders frames in the R3F viewport; **Analytics** plots time series; **Events** annotate the timeline.
7. User asks the **AI Copilot** to interpret; the AI receives trajectory summary + provenance and returns a grounded explanation / next-experiment suggestion.

---

## 11. Cross-cutting concerns

- **Testing:** engine has unit tests per module, property-based tests (mass/energy conservation invariants), and **golden-trajectory regression tests** (a fixed seed+config must reproduce a stored trajectory). Backend has API/integration tests; frontend has component + interaction tests.
- **Observability:** structured logging, run metrics, solver timing; simulation health (step time, LP feasibility) surfaced to operators.
- **Security:** JWT auth, RBAC per project, input validation everywhere, AI output sandboxed behind schema validation, no secrets in code.
- **Performance knobs:** module step multipliers, coarse vs. fine model versions, frame decimation for streaming, instancing/LOD budgets.
- **Deployment:** Render for dev (managed Postgres + web + worker services); containerized for a later lift to AWS/GCP (managed Postgres, object storage, autoscaled workers).

---

## 12. Proposed module implementation order (Step 2 preview)

Build the **engine bottom-up first** — it de-risks the whole product, because if the science can't grow a cell, nothing else matters.

1. **Engine kernel + CellState + Scheduler** (with a trivial toy module) — proves the multi-algorithm loop and checkpointing.
2. **Environment + Transport + a minimal Metabolism (FBA)** — first *emergent growth* on nutrients.
3. **Gene expression (SSA) + Division + Death classification** — full life cycle emerges.
4. **Provenance/reproducibility + golden-trajectory tests.**
5. **Backend: Auth + Design + Simulation Control + WebSocket streaming.**
6. **Frontend: Design Studio + Analytics + basic 3D viewport (viz mapper + instancing).**
7. **AI Copilot (NL→design, interpretation) with schema guardrails + RAG.**
8. **Cell-type registry expansion (minimal → cancer/immune/stem).**
9. **VR/WebXR layer.**

Each module ships with clean architecture, documentation, tests, and production quality — no shortcuts.

---

## 13. Locked MVP decisions (2026-07-03)

These four choices are settled and constrain Step 2:

1. **Metabolism fidelity:** start with constraint-based **FBA** (COBRApy). Fast, genome-scale, parameter-light. Kinetic ODE detail is added later as a *second model version*, not the MVP path.
2. **First reference cell type:** **minimal/synthetic cell** (JCVI-syn3.0-like) — smallest well-characterized biology, easiest to validate emergent behavior. Cancer/immune/stem come later as registry plugins on the proven kernel.
3. **MVP optimizes for the interactive coarse model** — a fast, near-real-time model that drives the full *design → simulate → observe* loop. High-fidelity batch fidelity is a later, second model version.
4. **Job execution at MVP:** **Postgres-backed job queue** on Render (no separate broker). Swap to Redis/RabbitMQ only when concurrency demands it.
```
