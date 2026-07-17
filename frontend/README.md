# vcs-frontend — Virtual Cell Studio UI

A React + TypeScript + Vite single-page app that lets you design a virtual cell,
run it on the backend, and **watch its autonomous lifecycle** — growth, gene
expression, replication, mutation, division, and death — live in the browser.

> **Milestone: Frontend MVP (M7) + AI copilot UI (M8) + VR (M12).** Auth,
> projects/designs, full simulation control, a WebSocket-driven live dashboard +
> lifecycle timeline, a React Three Fiber 3D cell viewer with an **"Enter VR"**
> immersive mode (WebXR), and an AI copilot ("Design with AI" + grounded per-run Q&A).

## Architecture

```
src/
├── api/
│   ├── client.ts       # fetch wrapper: token storage, JSON/error handling, WS url
│   ├── endpoints.ts    # typed functions: auth / projects / designs / simulations
│   └── types.ts        # TS mirrors of the backend Pydantic schemas
├── auth/AuthContext.tsx      # JWT auth provider (login/register/logout)
├── stream/
│   ├── streamState.ts        # pure reducer for the frame/event stream (unit-tested)
│   └── useSimulationStream.ts# React hook wrapping the WebSocket
├── components/
│   ├── charts/LineChart.tsx  # dependency-free SVG time-series chart
│   ├── charts/StatTile.tsx   # KPI tile
│   ├── Dashboard.tsx         # live KPIs + charts from the frame stream
│   ├── EventTimeline.tsx     # lifecycle event log (division, mutation, death…)
│   ├── CellViewer.tsx        # React Three Fiber 3D cell (size=mass, colour=status)
│   ├── SimulationControls.tsx# start / pause / resume / stop
│   ├── Layout.tsx, ProtectedRoute.tsx, theme.ts
└── pages/                    # Login, Register, Projects, Project, Simulation
```

**Data flow.** REST calls (via `api/`) drive CRUD and control; the live view opens a
WebSocket (`/ws/simulations/{id}?token=`) and folds each `frame`/`event`/`status`
message into state through the pure `reduceStream` reducer. The dashboard, timeline,
and 3D viewer are all **projections of that stream** — no biology is computed on the
client.

**3D viewer.** The cell is a sphere whose radius tracks biomass, whose colour tracks
lifecycle status (green → amber → orange → grey), whose surface fades with membrane
integrity, and which pulses on each division. It reads simulation state only.

**VR / WebXR (Module 12).** The same scene graph renders immersively via
[`@react-three/xr`](https://github.com/pmndrs/xr). An **"Enter VR"** button on the
simulation viewer starts an immersive session on a WebXR headset (the button is
disabled if no headset/WebXR is detected). In VR you see the cell, its **membrane**,
**internal compartments** (energy-coloured spheres, red when stressed), the
extracellular **nutrient gradient** (concentric shells), and floating **info panels**
(vitals, glucose/nutrients, compartment energy) that billboard toward you. The normal
browser viewer is unchanged — mouse-drag to orbit, scroll to zoom (via
`OrbitControls`, auto-disabled inside VR where the headset drives the camera).

- The scene is shared: `components/vr/CellScene.tsx` renders in both the browser
  `<Canvas>` and inside `<XR>`. Panels are canvas-texture planes (`LabelPanel`) — no
  DOM overlay, so they work in immersive mode. Panel text is built by the pure,
  unit-tested `components/vr/labels.ts`.
- The browser WebXR **emulator** devtools (`@iwer/devui`) is disabled and stubbed: it
  conflicts with React Three Fiber v8's zustand. Real-headset VR is unaffected; to
  emulate a headset without hardware, use a browser WebXR emulator extension.

## Run it locally

Three processes: engine (installed), backend API, and this dev server.

```bash
# 1. Backend (from repo root)
cd engine   && pip install -e ".[dev]"
cd ../backend && pip install -e ".[dev]" && uvicorn app.main:app --reload   # :8000

# 2. Frontend
cd ../frontend && npm install && npm run dev                                # :5173
```

Open http://localhost:5173, register an account, create a project → a design
(pick the **evolution** scenario to see mutations), and hit **Run**. The Vite dev
server proxies `/api` and `/ws` to the backend on :8000, so no CORS setup is needed.

For a production build point the app at your API:

```bash
VITE_API_URL=https://api.example.com npm run build   # emits dist/
```

## Scripts

| Command | What |
|---|---|
| `npm run dev` | Vite dev server with API/WS proxy |
| `npm run build` | Type-check (`tsc -b`) then production build |
| `npm run typecheck` | `tsc --noEmit` |
| `npm test` | Vitest (stream reducer, API client, timeline component) |

## Notes

- Auth token is stored in `localStorage` and sent as a bearer header; the WebSocket
  passes it as a query param (browsers can't set WS headers).
- The stream reducer is intentionally pure and separately tested; the 3D canvas is
  excluded from unit tests (no WebGL in jsdom) and validated via typecheck/build.
