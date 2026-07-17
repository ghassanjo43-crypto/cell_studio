# Deploying Virtual Cell Studio

Three deployable pieces: the **engine** (a library the backend installs), the
**backend** API + a **worker** process, and the **frontend** static site. This guide
covers a production deploy on [Render](https://render.com) via the blueprint
(`render.yaml`), plus the manual steps if you deploy elsewhere.

## Topology

```
                 ┌──────────────┐        ┌────────────────────┐
   Browser ─────▶│  Frontend    │──REST/WS──▶│  Backend (web)     │
   (static SPA)  │  (static)    │        │  uvicorn app.main  │
                 └──────────────┘        └─────────┬──────────┘
                                                   │  sets jobs QUEUED
                                        ┌──────────▼──────────┐
                                        │  Postgres (queue +  │
                                        │  frames/events/     │
                                        │  checkpoints)       │
                                        └──────────▲──────────┘
                                                   │  claims + runs jobs
                                        ┌──────────┴──────────┐
                                        │  Worker process     │
                                        │  app.worker_main    │
                                        └─────────────────────┘
```

The **worker is a separate process** (`VCS_WORKER_MODE=external`): the web service
never runs simulations, it only enqueues them. The worker(s) claim queued jobs from
the `simulations` table using `FOR UPDATE SKIP LOCKED`, so you can run several workers
safely. Jobs are checkpointed, so a worker restart resumes runs bit-for-bit.

## One-click on Render

1. Push this repo to GitHub.
2. Render Dashboard → **New → Blueprint** → select the repo. Render reads
   `render.yaml` and provisions: a Postgres DB, the backend web service, the worker,
   and the frontend static site — with env vars wired between them.
3. After the first deploy, set **`ANTHROPIC_API_KEY`** on the `vcs-backend` service
   (Dashboard → Environment) to enable the AI copilot. Everything else works without it.
4. Open the frontend URL, register, and run a simulation.

The blueprint sets `VCS_ENVIRONMENT=production`, a generated `VCS_JWT_SECRET` (shared
between web and worker), the Postgres `VCS_DATABASE_URL`, `VCS_WORKER_MODE=external`,
and `VCS_CORS_ORIGINS` = the frontend origin.

## Manual / other hosts

**Database schema (Alembic).** Postgres schema is managed by migrations, not
`create_all`:

```bash
cd backend
VCS_DATABASE_URL=postgres://…  alembic upgrade head
```

Run this once per deploy (the blueprint does it in the backend `buildCommand`). To
evolve the schema later: edit the models, then
`alembic revision --autogenerate -m "…"` and commit the new file in
`backend/migrations/versions/`.

**Backend (web):**

```bash
cd backend
pip install -e ../engine && pip install -e '.[prod]'   # [prod] adds the psycopg driver
export VCS_ENVIRONMENT=production
export VCS_DATABASE_URL=postgres://…
export VCS_JWT_SECRET="$(openssl rand -hex 32)"
export VCS_CORS_ORIGINS=https://your-frontend.example.com
export VCS_WORKER_MODE=external
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Worker (separate process, same DB + same `VCS_JWT_SECRET`):**

```bash
cd backend
export VCS_ENVIRONMENT=production VCS_DATABASE_URL=postgres://… VCS_WORKER_MODE=external
export VCS_JWT_SECRET=…  VCS_CORS_ORIGINS=https://your-frontend.example.com
python -m app.worker_main
```

Scale by running more worker processes — they coordinate through the DB queue.

**Frontend (static):**

```bash
cd frontend
VITE_API_URL=https://your-backend.example.com npm ci && npm run build   # emits dist/
```

Serve `dist/` from any static host/CDN with an SPA fallback (all routes → `index.html`).
The app derives the WebSocket URL from `VITE_API_URL` (http→ws); override with
`VITE_WS_URL` only if the WS host differs.

> Behind a TLS-intercepting proxy, `npm` may need `NODE_OPTIONS=--use-system-ca`.

## Safe production configuration

`check_production_config` runs at startup (web **and** worker) and **refuses to boot**
in production if any of these are unsafe:

- `VCS_JWT_SECRET` is still the development default,
- `VCS_DATABASE_URL` is SQLite (must be Postgres), or
- `VCS_CORS_ORIGINS` is empty.

Set them before deploying. CORS is locked to the configured origins with credentials
allowed (never a wildcard).

## Persistent storage strategy

All durable state lives in **Postgres**:

| Data | Table | Notes |
|---|---|---|
| Users, projects, designs | `users`, `projects`, `designs` | Small, relational. |
| Simulation jobs (the queue) | `simulations` | Status + control flags. |
| Trajectory frames | `frames` | One JSON row per persisted step. |
| Lifecycle/mutation events | `sim_events` | One JSON row per event. |
| Engine checkpoints | `checkpoints` | Full state + RNG bit-state (JSON). |

Frame volume is bounded with `VCS_FRAME_STRIDE` (persist every Nth step) — raise it
for long runs. This is the MVP strategy; the architecture reserves a future path of
moving bulk `frames`/`checkpoints` to object storage (Parquet) referenced from
Postgres, with **no API change** — the read endpoints and WebSocket stream stay the
same. Use a managed Postgres with backups; checkpoints make runs resumable across
restarts.

## Health & smoke checks

- `GET /health` → `{"status":"ok"}` (the backend health check path).
- `GET /openapi.json` and `/docs` (Swagger) expose the full API.
- The deploy-style smoke tests (`backend/tests/test_deploy.py`) verify URL
  normalization, the production-safety gate, CORS headers, and the external
  worker/queue path end-to-end.
