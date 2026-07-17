# vcs-backend — Virtual Cell Studio API

A FastAPI service that lets clients design, run, and **stream** autonomous virtual
synthetic-cell simulations. It is a thin **control + persistence** layer over the
standalone [`vcs-engine`](../engine) simulation core — all biology lives in the
engine; the backend never duplicates it.

> **Milestone: Backend scaffold (Module 6) + AI copilot (Module 8).** JWT auth,
> user/project/design CRUD, a Postgres-backed simulation job queue (no Redis),
> checkpoint + trajectory/event persistence, full simulation control, WebSocket
> streaming, and an AI copilot (NL→validated design + grounded interpretation).

## Architecture

```
Client ──REST──▶ FastAPI routers ──▶ services ──▶ models (SQLAlchemy)
   │                                     │
   └──WebSocket──▶ ws router             ├──▶ WorkerManager ──▶ SimulationRunner
        (frames + events, DB-polled)     │        (inline or background thread)
                                         └──▶ engine_adapter ──▶ vcs_engine  ← ONLY engine import
```

- **`engine_adapter.py`** is the single bridge to `vcs_engine`: it maps a
  `DesignConfig` to a `build_*_scenario` call and extracts compact frames/events.
  No biological logic lives in the backend.
- **The `simulations` table is the job queue** (its `status` column + `pause/stop`
  control flags). No external broker is needed, per the MVP infra decision.
- **The worker** runs a job in batches, checking the DB for pause/stop between
  batches and writing frames, events, and checkpoints. It runs **inline** (tests /
  single-process dev) or on a **background thread** (`VCS_WORKER_BACKGROUND=true`).
- **Reproducibility & resume** come free from the engine: a paused/stopped job
  saves a full engine checkpoint (state + per-module RNG bit-state) and resumes
  bit-for-bit.

## Layout

```
backend/app/
├── main.py            # app factory; wires config, DB, worker, routers
├── config.py          # settings (env: VCS_*)
├── db.py              # engine / session factory / Base
├── models.py          # SQLAlchemy models (users, projects, designs, simulations,
│                      #   frames, sim_events, checkpoints)
├── security.py        # PBKDF2 password hashing + JWT
├── deps.py            # get_db, current-user, worker dependencies
├── engine_adapter.py  # the ONLY import of vcs_engine
├── worker.py          # SimulationRunner + WorkerManager (the job queue runner)
├── schemas/           # Pydantic: auth, project, design (mirrors engine config), simulation
├── services/          # auth / project / simulation business logic
└── routers/           # auth, projects, simulations, ws
```

## Setup

```bash
pip install -e ../engine        # the engine must be installed first
pip install -e ".[dev]"
uvicorn app.main:app --reload   # http://127.0.0.1:8000/docs  (Swagger UI)
```

Configuration is via `VCS_`-prefixed env vars (see `config.py`): `VCS_DATABASE_URL`
(defaults to SQLite; set a Postgres URL in production), `VCS_JWT_SECRET`,
`VCS_WORKER_BACKGROUND`, etc.

## API

Interactive docs at `/docs` (Swagger) and `/redoc`; the schema at `/openapi.json`.

| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/register` | Create a user |
| POST | `/auth/token` | Log in (OAuth2 password grant) → bearer token |
| GET  | `/auth/me` | Current user |
| POST/GET | `/projects` | Create / list projects |
| POST/GET | `/projects/{id}/designs` | Create / list designs (cell + environment config) |
| GET  | `/designs/{id}` | Read a design |
| POST | `/simulations` | Create a simulation from a design |
| GET  | `/simulations/{id}` | Read a simulation |
| GET  | `/simulations/{id}/status` | Status + frame/event counts |
| POST | `/simulations/{id}/start` | Enqueue & run |
| POST | `/simulations/{id}/pause` | Request pause (checkpoints) |
| POST | `/simulations/{id}/resume` | Resume from checkpoint |
| POST | `/simulations/{id}/stop` | Stop |
| GET  | `/simulations/{id}/frames` | Trajectory frames (`?since_step=`) |
| GET  | `/simulations/{id}/events` | Lifecycle/mutation events (`?since_step=`) |
| WS   | `/ws/simulations/{id}?token=` | Live stream of frames + events |
| POST | `/ai/design` | Natural language → **validated** `DesignConfig` |
| POST | `/ai/simulations/{id}/interpret` | Grounded Q&A about a run |

### AI copilot (`app/ai/`)

The copilot is a thin, provider-abstracted layer (`AIProvider` → Claude via the
Anthropic SDK, model `claude-opus-4-8`; OpenAI as an optional fallback). It does two
things, both with hard guardrails:

- **NL → design.** The model fills a permissive tool schema; the result is then
  validated against the Pydantic `DesignConfig`. An out-of-range or unknown value is
  **rejected (422)** — the LLM proposes, the schema disposes, and a design is only
  ever created from a validated config.
- **Grounded interpretation.** For "Why did the cell die?" / "Why did growth stop?" /
  "Suggest the next experiment", the backend builds a factual summary from the run's
  **persisted frames and events** and instructs the model to answer *only* from that
  summary — no invented biology. The grounding text is returned alongside the answer
  for transparency.

Configure with `ANTHROPIC_API_KEY` (or an `ant auth login` profile). `VCS_AI_MODEL`
overrides the model; set `VCS_OPENAI_MODEL` to enable the OpenAI fallback. Tests inject
a fake provider, so no key is needed to run them.

### Design configuration

`DesignConfig` mirrors the engine's scenario builders. `scenario` selects
`minimal` | `lifecycle` | `evolution`; the remaining fields (seed, glucose, masses,
mutation rate, `dt`, `max_steps`, …) map straight onto the corresponding
`build_*_scenario` parameters.

### WebSocket messages

```jsonc
{"kind": "frame", "step": 42, "time": 4.2, "data": {"mass": 0.13, "alive": true, ...}}
{"kind": "event", "step": 90, "time": 9.0, "type": "division", "data": {...}}
{"kind": "status", "status": "DONE", "done": true}   // final; socket then closes
```

## Tests & type checks

```bash
python -m pytest      # auth, CRUD, sim flow, control, websocket, engine adapter
python -m mypy        # strict
```

Tests use an in-memory SQLite DB and an **inline** worker, so the full
create → start → stream flow runs deterministically without a server or Postgres.
