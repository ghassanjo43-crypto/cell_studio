// The Cell Explorer: an immersive, data-driven scientific view of the simulated
// cell. Renders the biological scene (browser + VR), a click-to-inspect panel, and a
// timeline that replays recorded biological events. Every visual is bound to frame
// data — see ./scene/* and ./inspect.ts.

import { Canvas } from "@react-three/fiber";
import { XR, XROrigin, createXRStore } from "@react-three/xr";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ACESFilmicToneMapping } from "three";
import type { Frame, FrameData, HeatmapMetric, SimEvent } from "../../api/types";
import { CellExplorerScene } from "./CellExplorerScene";
import { AutoQuality } from "./cell/AutoQuality";
import { metabolicActivityFrom, radiusForMass } from "./cell/biomap";
import type { HoverFn } from "./cell/interact";
import { PostFX } from "./cell/PostFX";
import { qualitySettings, resolveQuality, type Quality, type QualityMode } from "./cell/quality";
import type { FocusRequest } from "./scene/Controls";
import { FigureCapture } from "./FigureCapture";
import { legendFor } from "./figure";
import { focusPresets, type FocusKey } from "./focus";
import { HoverTooltip } from "./HoverTooltip";
import { buildInspect, presentObjects } from "./inspect";
import type { ObjectId } from "./inspect";
import { InspectorPanel } from "./InspectorPanel";
import { legendItems } from "./legendItems";
import { cloneColorRGB, representativeCellFrame } from "./petri";
import { activeEvents, clampIndex, eventMarkers } from "./playback";
import { buildNarrationLog, narrationUpTo, type NarrationMode } from "./presentation/narration";
import { NarrationPanel } from "./presentation/NarrationPanel";
import { ScreenRecorder, type RecordOverlay } from "./presentation/recorder";
import { CINEMATIC_EVENTS, eventShot, tourScenes, type TourScene } from "./presentation/tour";
import { SceneLegend } from "./SceneLegend";
import { Timeline } from "./Timeline";

type Mode = "research" | "teaching" | "presentation" | "investor";
const MODES: Mode[] = ["research", "teaching", "presentation", "investor"];
const JUMP_TYPES: { type: string; label: string }[] = [
  { type: "mutation", label: "Mutation" },
  { type: "division", label: "Division" },
  { type: "survival_mode_entered", label: "Survival" },
  { type: "death", label: "Death" },
  { type: "clone_expansion", label: "Clone expansion" },
  { type: "population_extinct", label: "Collapse" },
];

const QUALITY_OPTIONS: QualityMode[] = ["auto", "low", "medium", "high"];

const HEATMAPS: { key: HeatmapMetric; label: string }[] = [
  { key: "clone", label: "Clones" },
  { key: "population", label: "Density" },
  { key: "nutrient", label: "Nutrient" },
  { key: "mutation", label: "Mutation" },
  { key: "atp", label: "ATP" },
];

export interface SimControls {
  status: import("../../api/types").SimulationStatus;
  busy: boolean;
  onStart: () => void;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
}

/** Imperative actions the command palette / shortcuts invoke on the viewer. */
export interface CellExplorerApi {
  togglePlay: () => void;
  goLive: () => void;
  restart: () => void;
  resetCamera: () => void;
  enterVR: () => void;
  exportFigure: () => void;
  toggleRecord: () => void;
  setPresentation: (on: boolean) => void;
  toggleLegend: () => void;
  toggleTimeline: () => void;
  focus: (key: import("./focus").FocusKey) => void;
  focusSelected: () => void;
  setQuality: (q: QualityMode) => void;
  setLegend: (b: boolean) => void;
  setDock: (b: boolean) => void;
  closeSettings: () => void;
  toggleCinematic: () => void;
  enterInside: () => void;
}

/** Snapshot pushed to the workspace for building commands + persisting prefs. */
export interface ViewerState {
  vrAvailable: boolean;
  presenting: boolean;
  recording: boolean;
  cinematic: boolean;
  quality: QualityMode;
  legend: boolean;
  dock: boolean;
  focusKeys: string[];
}

interface CellExplorerProps {
  frames: Frame[];
  events: SimEvent[];
  connected: boolean;
  title?: string;
  /** Simulation (worker) controls, rendered into the floating toolbar. */
  sim?: SimControls;
  /** DOM node in the right sidebar to portal the inspector into. */
  inspectorSlot?: HTMLElement | null;
  fullscreen?: boolean;
  onToggleFullscreen?: () => void;
  /** Imperative handle set by the workspace (for commands / shortcuts). */
  apiRef?: React.MutableRefObject<CellExplorerApi | null>;
  onViewerState?: (s: ViewerState) => void;
  initialQuality?: QualityMode;
  initialLegend?: boolean;
  initialDock?: boolean;
}

export function CellExplorer({
  frames, events, connected, title = "Virtual Cell Studio",
  sim, inspectorSlot, fullscreen = false, onToggleFullscreen,
  apiRef, onViewerState, initialQuality, initialLegend, initialDock,
}: CellExplorerProps) {
  const store = useMemo(() => createXRStore({ emulate: false }), []);
  const [vrSupported, setVrSupported] = useState<boolean | null>(null);
  const captureRef = useRef<(() => void) | null>(null);

  const [index, setIndex] = useState(0);
  const [following, setFollowing] = useState(true);
  const [playing, setPlaying] = useState(false);
  const [explore, setExplore] = useState(false);
  const [selected, setSelected] = useState<ObjectId | null>(null);
  const [heatmapMetric, setHeatmapMetric] = useState<HeatmapMetric>("clone");
  const [enteredCell, setEnteredCell] = useState<number | null>(null);
  const [qualityMode, setQualityMode] = useState<QualityMode>(initialQuality ?? "high");
  const [autoTier, setAutoTier] = useState<Quality>("high");
  const [hovered, setHovered] = useState<{ id: ObjectId; x: number; y: number } | null>(null);
  const [showLegend, setShowLegend] = useState(initialLegend ?? true);
  const [focus, setFocus] = useState<FocusRequest | null>(null);
  const [mode, setMode] = useState<Mode>("teaching");
  const [cinematic, setCinematic] = useState<string | null>(null);
  const [showNarration, setShowNarration] = useState(true);
  const [recording, setRecording] = useState(false);
  const [showDock, setShowDock] = useState(initialDock ?? true);
  const [showSettings, setShowSettings] = useState(false);
  const [cinematicMode, setCinematicMode] = useState(false);

  const rendererRef = useRef<{ domElement: HTMLCanvasElement } | null>(null);
  const recorderRef = useRef(new ScreenRecorder());
  const frameRef = useRef<FrameData | null>(null);
  const scenesRef = useRef<TourScene[]>([]);
  const overlayRef = useRef<RecordOverlay>({ title: "", subtitle: "", date: "", legend: [] });

  const quality = resolveQuality(qualityMode, autoTier);
  const qsettings = useMemo(() => qualitySettings(quality), [quality]);

  // Stable so the memoised scene doesn't re-render on hover.
  const onHover = useCallback<HoverFn>((id, x, y) => {
    setHovered(id ? { id, x: x ?? 0, y: y ?? 0 } : null);
  }, []);

  // VR capability probe (real headset only; emulator disabled).
  useEffect(() => {
    const xr = (navigator as unknown as { xr?: { isSessionSupported?: (m: string) => Promise<boolean> } }).xr;
    if (!xr?.isSessionSupported) {
      setVrSupported(false);
      return;
    }
    xr.isSessionSupported("immersive-vr").then(setVrSupported).catch(() => setVrSupported(false));
  }, []);

  // Follow the live run: keep the position pinned to the newest frame.
  useEffect(() => {
    if (following && frames.length) setIndex(frames.length - 1);
  }, [following, frames.length]);

  // Replay playback: advance through recorded history while paused-from-live.
  useEffect(() => {
    if (!playing || following) return;
    const id = window.setInterval(() => {
      setIndex((i) => {
        const last = frames.length - 1;
        if (i >= last) {
          setPlaying(false);
          return last;
        }
        return i + 1;
      });
    }, 120);
    return () => window.clearInterval(id);
  }, [playing, following, frames.length]);

  const idx = clampIndex(index, frames.length);
  const frame = frames.length ? frames[idx].data : null;
  const isPetri = !!frame?.petri;

  // "Enter cell": render the full single-cell explorer for a representative cell of
  // the dish. viewFrame is the synthetic single-cell frame while entered.
  const entered = enteredCell !== null && isPetri;
  const rep = entered && frame?.petri ? representativeCellFrame(frame.petri.cells, enteredCell!, frame.petri) : null;
  const viewFrame = rep ?? frame;

  // Growth-rate–derived metabolic activity (0..1) from the biomass slope — a real,
  // data-driven measure that drives ATP/ribosome intensity in the renderer.
  const metabolicActivity = useMemo(() => {
    if (frames.length < 2 || idx < 1) return 0;
    const w = Math.max(0, idx - 4);
    const a = frames[w];
    const b = frames[idx];
    return metabolicActivityFrom(b.data.mass ?? 0, a.data.mass ?? 0, (b.time - a.time) || 1);
  }, [frames, idx]);

  const markers = useMemo(() => eventMarkers(events, frames), [events, frames]);
  const activeTypes = useMemo(() => new Set(activeEvents(markers, idx).map((m) => m.type)), [markers, idx]);
  const present = useMemo(() => presentObjects(viewFrame), [viewFrame]);
  const info = selected ? buildInspect(selected, viewFrame) : null;

  // Figure-export metadata + legend (grounded in the current frame).
  const figureMeta = useMemo(() => {
    const p = frame?.petri;
    const subtitle = p
      ? `Petri dish ${p.grid[0]}×${p.grid[1]} · ${p.alive} cells · ${p.colonies}/${p.n_clones} colonies · step ${p.step}`
      : frame?.population
      ? `Colony · ${frame.population.alive} living cells · step ${frame.population.step}`
      : `${frame?.status ?? "cell"} · biomass ${(frame?.mass ?? 0).toFixed(3)} gDW · step ${frames[idx]?.step ?? 0}`;
    return { title, subtitle };
  }, [frame, title, frames, idx]);

  const figureLegend = useMemo(() => {
    if (!frame?.petri) return [];
    const clones = Array.from({ length: frame.petri.n_clones }, (_, i) => {
      const [r, g, b] = cloneColorRGB(i);
      return `rgb(${r},${g},${b})`;
    });
    return legendFor(heatmapMetric, clones);
  }, [frame, heatmapMetric]);

  const focusList = useMemo(() => focusPresets(frame), [frame]);
  function focusOn(preset: (typeof focusList)[number]) {
    setSelected(preset.id);
    setHovered(null);
    setFocus({ distance: preset.distance, target: preset.target, nonce: Date.now() });
  }
  function focusByKey(key: FocusKey) {
    const preset = focusList.find((f) => f.key === key);
    if (preset) focusOn(preset);
  }
  function focusSelected() {
    if (!selected) return;
    const dist = selected === "nucleoid" ? 1.9 : selected === "membrane" ? 4.5 : selected === "signalling" ? 4.2
      : selected === "cytosol" ? 3 : selected === "nutrients" ? 9 : selected.startsWith("energy") ? 3
      : selected.startsWith("petri") ? 5 : 4;
    setFocus({ distance: dist, target: [0, 0, 0], duration: 0.8, nonce: performance.now() });
  }

  // ---------- Presentation engine ----------
  const presenting = mode === "presentation";
  const narrationMode: NarrationMode = presenting ? "teaching" : mode;
  const currentStep = frames.length ? frames[idx].step : 0;
  const narrationLog = useMemo(
    () => buildNarrationLog(frames, events, narrationMode),
    [frames, events, narrationMode],
  );
  const narrationLines = useMemo(() => narrationUpTo(narrationLog, currentStep), [narrationLog, currentStep]);

  // Latest data for the (ref-driven) tour + recorder overlay.
  frameRef.current = viewFrame;
  scenesRef.current = tourScenes(viewFrame);
  overlayRef.current = {
    title,
    subtitle: figureMeta.subtitle,
    date: new Date().toLocaleString(),
    legend: legendItems(viewFrame, heatmapMetric),
    narration: cinematic ?? (narrationLines.length ? narrationLines[narrationLines.length - 1].text : undefined),
  };

  // Cinematic tour: cycle scenes while presenting.
  useEffect(() => {
    if (!presenting) {
      setCinematic(null);
      return;
    }
    let i = 0;
    let timer = 0;
    const play = () => {
      const scenes = scenesRef.current;
      if (!scenes.length) {
        timer = window.setTimeout(play, 1000);
        return;
      }
      const s = scenes[i % scenes.length];
      setFocus({ distance: s.distance, target: s.target, duration: 1.4, nonce: performance.now() });
      setSelected(s.id);
      setCinematic(s.caption(frameRef.current));
      i += 1;
      timer = window.setTimeout(play, s.seconds * 1000);
    };
    play();
    return () => window.clearTimeout(timer);
  }, [presenting]);

  // Event-driven cinematics: cut to a shot when an important event is on screen.
  useEffect(() => {
    if (!presenting) return;
    const hit = CINEMATIC_EVENTS.find((t) => activeTypes.has(t));
    if (!hit) return;
    const shot = eventShot(hit, frameRef.current);
    if (shot) {
      setFocus({ distance: shot.distance, target: shot.target, duration: 1.0, nonce: performance.now() });
      setSelected(shot.id);
      setCinematic(shot.caption);
    }
  }, [activeTypes, presenting]);

  function toggleRecord() {
    const r = recorderRef.current;
    if (r.recording) {
      r.stop();
      setRecording(false);
    } else if (rendererRef.current) {
      r.start(rendererRef.current.domElement, () => overlayRef.current);
      setRecording(true);
    }
  }

  function jumpToEvent(type: string) {
    const ms = markers.filter((m) => m.type === type);
    if (!ms.length) return;
    const next = ms.find((m) => m.index > idx) ?? ms[0];
    onScrub(next.index);
    if (presenting) {
      const s = eventShot(type, frameRef.current);
      if (s) setFocus({ distance: s.distance, target: s.target, duration: 1.0, nonce: performance.now() });
    }
  }

  const jumpAvailable = useMemo(() => {
    const present = new Set(markers.map((m) => m.type));
    return JUMP_TYPES.filter((j) => present.has(j.type));
  }, [markers]);

  const canEnter = !entered && selected?.startsWith("petricell.") ? Number(selected.slice("petricell.".length)) : null;

  function enterCell() {
    if (canEnter !== null) {
      setEnteredCell(canEnter);
      setSelected(null);
    }
  }
  function exitCell() {
    setEnteredCell(null);
  }

  function onScrub(i: number) {
    setFollowing(false);
    setIndex(i);
  }
  function onTogglePlay() {
    if (following) setFollowing(false);
    setPlaying((p) => !p);
  }
  function onLive() {
    setPlaying(false);
    setFollowing(true);
    if (frames.length) setIndex(frames.length - 1);
  }
  // Stop and re-run the animation: leave live-follow, jump to the first frame, and
  // play the recorded history from the start.
  function restartReplay() {
    if (!frames.length) return;
    setFollowing(false);
    setIndex(0);
    setPlaying(true);
  }
  function resetCamera() {
    const dist = frame?.petri ? 12 : 7;
    setFocus({ distance: dist, target: [0, 0, 0], duration: 0.8, nonce: performance.now() });
  }
  function enterInside() {
    const R = radiusForMass(frame?.mass ?? 0.001);
    // A long, eased push that travels *through* the membrane and settles deep inside,
    // framed off-centre and low so the DNA towers over an off-axis composition (rule of
    // thirds) — an "entering another world" glide rather than a cut. The straight dolly
    // crosses the membrane radius while the atmosphere thickens, selling the transition.
    setFocus({ distance: Math.max(0.5, R * 0.4), target: [R * 0.4, R * 0.28, 0], duration: 2.7, nonce: performance.now() });
  }
  function toggleCinematic() {
    setCinematicMode((c) => {
      if (!c) enterInside(); // entering cinematic → move inside the cytoplasm
      return !c;
    });
  }

  // Imperative API for the workspace command palette / shortcuts (fresh each render).
  if (apiRef) {
    apiRef.current = {
      togglePlay: onTogglePlay,
      goLive: onLive,
      restart: restartReplay,
      resetCamera,
      enterVR: () => store.enterVR(),
      exportFigure: () => captureRef.current?.(),
      toggleRecord,
      setPresentation: (on) => setMode(on ? "presentation" : "teaching"),
      toggleLegend: () => setShowLegend((s) => !s),
      toggleTimeline: () => setShowDock((s) => !s),
      focus: focusByKey,
      focusSelected,
      setQuality: setQualityMode,
      setLegend: setShowLegend,
      setDock: setShowDock,
      closeSettings: () => setShowSettings(false),
      toggleCinematic,
      enterInside,
    };
  }

  // Report viewer state upward (for commands + persistence) — only when it changes,
  // so the per-frame stream doesn't trigger extra work.
  const lastViewerState = useRef("");
  useEffect(() => {
    const s = {
      vrAvailable: !!vrSupported,
      presenting,
      recording,
      cinematic: cinematicMode,
      quality: qualityMode,
      legend: showLegend,
      dock: showDock,
      focusKeys: focusList.map((f) => f.key),
    };
    const key = JSON.stringify(s);
    if (key !== lastViewerState.current) {
      lastViewerState.current = key;
      onViewerState?.(s);
    }
  }, [onViewerState, vrSupported, presenting, recording, cinematicMode, qualityMode, showLegend, showDock, focusList]);

  // Simulation (worker) control state for the toolbar.
  const st = sim?.status;
  const canStart = st === "CREATED" || st === "STOPPED";
  const canPause = st === "RUNNING" || st === "QUEUED";
  const canResume = st === "PAUSED";
  const canStop = !!st && !["DONE", "STOPPED", "FAILED"].includes(st);

  const inspectorEl = (
    <InspectorPanel
      info={info}
      present={present}
      selected={selected}
      onSelect={setSelected}
      onClear={() => setSelected(null)}
      onEnter={canEnter !== null ? enterCell : undefined}
    />
  );

  return (
    <div className={`viewer-shell ${fullscreen ? "is-fullscreen" : ""}`}>
      {/* Floating toolbar */}
      <div className="viewer-floating-toolbar">
        {sim ? (
          <span className="tb-group">
            {canPause ? (
              <button className="tb-btn" disabled={sim.busy} onClick={sim.onPause} title="Pause">⏸</button>
            ) : canResume ? (
              <button className="tb-btn" disabled={sim.busy} onClick={sim.onResume} title="Resume">⏵</button>
            ) : (
              <button className="tb-btn tb-primary" disabled={sim.busy || !canStart} onClick={sim.onStart} title="Start">▶</button>
            )}
            <button className="tb-btn tb-danger" disabled={sim.busy || !canStop} onClick={sim.onStop} title="Stop">⏹</button>
            {st ? <span className={`status-badge status-${st.toLowerCase()}`}>{st}</span> : null}
          </span>
        ) : null}

        <span className="tb-group">
          <button className={`tb-btn ${following ? "tb-live" : ""}`} onClick={onLive} title="Follow the live run" disabled={!frames.length}>●</button>
          <button className="tb-btn" onClick={restartReplay} title="Replay animation from the start" disabled={!frames.length}>⟳</button>
          <button className="tb-btn" onClick={resetCamera} title="Reset camera">🏠</button>
          <button className="tb-btn" onClick={enterInside} title="Inside cell — fly into the cytoplasm">⊙</button>
          <button className={`tb-btn ${cinematicMode ? "tb-live" : ""}`} onClick={toggleCinematic} title="Cinematic mode — immersive molecular environment">🎞</button>
          <button className="tb-btn" disabled={!vrSupported} onClick={() => store.enterVR()} title={vrSupported ? "Enter VR" : "VR unavailable"}>🥽</button>
          <button className="tb-btn" onClick={() => captureRef.current?.()} title="Export figure (PNG)">📷</button>
          <button className={`tb-btn ${recording ? "tb-danger" : ""}`} onClick={toggleRecord} title="Record movie (WebM)">🎬</button>
        </span>

        <span className="tb-group">
          <button
            className={`tb-btn ${presenting ? "tb-live" : "tb-primary"}`}
            onClick={() => setMode(presenting ? "teaching" : "presentation")}
            title="Presentation Mode — automatic cinematic tour"
          >
            {presenting ? "⏹ Tour" : "▶ Present"}
          </button>
          <label className="tb-select" title="Guided / narration mode">
            <select value={mode} onChange={(e) => setMode(e.target.value as Mode)}>
              {MODES.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </label>
        </span>

        {!entered && focusList.length ? (
          <span className="tb-group tb-focus" title="Focus the camera on a structure">
            <span className="tb-mini-label">Focus</span>
            {focusList.map((f) => (
              <button key={f.key} className="tb-btn tb-text" onClick={() => focusOn(f)} title={`Focus: ${f.label}`}>{f.label}</button>
            ))}
          </span>
        ) : null}

        {isPetri && !entered ? (
          <label className="tb-select" title="Heat-map field">
            <select value={heatmapMetric} onChange={(e) => setHeatmapMetric(e.target.value as HeatmapMetric)}>
              {HEATMAPS.map((h) => <option key={h.key} value={h.key}>{h.label}</option>)}
            </select>
          </label>
        ) : null}

        {entered ? <button className="tb-btn tb-primary" onClick={exitCell} title="Back to the dish">⬆ Exit</button> : null}

        <span className="tb-group tb-right">
          <label className="tb-select" title="Rendering quality">
            <select value={qualityMode} onChange={(e) => setQualityMode(e.target.value as QualityMode)}>
              {QUALITY_OPTIONS.map((q) => <option key={q} value={q}>{q === "auto" ? `auto·${quality}` : q}</option>)}
            </select>
          </label>
          <button className="tb-btn" onClick={onToggleFullscreen} title="Full screen (Esc to exit)">{fullscreen ? "🗗" : "⛶"}</button>
          <div className="tb-settings-wrap">
            <button className={`tb-btn ${showSettings ? "tb-active" : ""}`} onClick={() => setShowSettings((s) => !s)} title="Settings">⚙</button>
            {showSettings ? (
              <div className="viewer-settings-pop">
                <button className={`btn btn-small ${explore ? "btn-active" : ""}`} onClick={() => setExplore((e) => !e)}>🛰 Explore mode</button>
                <button className={`btn btn-small ${showLegend ? "btn-active" : ""}`} onClick={() => setShowLegend((s) => !s)}>🔑 Legend</button>
                <button className={`btn btn-small ${showNarration ? "btn-active" : ""}`} onClick={() => setShowNarration((s) => !s)}>💬 Narration</button>
                <div className="settings-hint">
                  {explore ? "WASD fly · QE up/down" : "drag orbit · scroll zoom"} · {connected ? "● live" : "○ idle"}
                </div>
              </div>
            ) : null}
          </div>
        </span>
      </div>

      {/* Viewer */}
      <div className="cell-viewer" data-testid="cell-viewer">
        <Canvas
          camera={{ position: [1.1, 0.7, 2.3], fov: 52 }}
          dpr={qsettings.dpr}
          gl={{ antialias: true, toneMapping: ACESFilmicToneMapping, toneMappingExposure: 1.05, preserveDrawingBuffer: true }}
          onCreated={({ gl }) => {
            rendererRef.current = gl;
          }}
          onPointerMissed={() => setSelected(null)}
        >
          <XR store={store}>
            <XROrigin position={[0, 1.2, 4]} />
            <CellExplorerScene
              frame={viewFrame}
              activeTypes={activeTypes}
              selected={selected}
              onSelect={setSelected}
              onHover={onHover}
              explore={explore}
              heatmapMetric={heatmapMetric}
              metabolicActivity={metabolicActivity}
              densityScale={qsettings.densityScale}
              focus={focus}
              cinematic={cinematicMode}
            />
            <PostFX settings={qsettings} cinematic={cinematicMode} />
            <AutoQuality enabled={qualityMode === "auto"} tier={autoTier} onTier={setAutoTier} />
            <FigureCapture
              registerRef={captureRef}
              meta={figureMeta}
              legend={figureLegend}
              petriGridW={frame?.petri?.grid[1]}
            />
          </XR>
        </Canvas>
        {showLegend ? <SceneLegend frame={viewFrame} metric={heatmapMetric} /> : null}
        {showNarration ? <NarrationPanel lines={narrationLines} mode={narrationMode} /> : null}
        {presenting && cinematic ? <div className="cinematic-caption">{cinematic}</div> : null}
        {recording ? <div className="rec-badge">⏺ REC</div> : null}
        {hovered ? (
          <HoverTooltip
            id={hovered.id}
            x={hovered.x}
            y={hovered.y}
            frame={viewFrame}
            onClick={() => {
              setSelected(hovered.id);
              setHovered(null);
            }}
          />
        ) : null}
      </div>

      {/* Bottom replay dock */}
      <div className={`timeline-dock ${showDock ? "" : "dock-collapsed"}`}>
        <button className="dock-handle" onClick={() => setShowDock((s) => !s)} title="Toggle timeline dock">
          {showDock ? "▾" : "▴"} Timeline · step {frames.length ? frames[idx].step : 0} · t={(frames.length ? frames[idx].time : 0).toFixed(2)}
        </button>
        {showDock ? (
          <div className="dock-body">
            {jumpAvailable.length ? (
              <div className="jump-bar">
                <span className="jump-label">Jump to:</span>
                {jumpAvailable.map((j) => (
                  <button key={j.type} className="btn btn-small" onClick={() => jumpToEvent(j.type)}>{j.label}</button>
                ))}
              </div>
            ) : null}
            <Timeline
              frames={frames}
              markers={markers}
              index={idx}
              following={following}
              playing={playing}
              onScrub={onScrub}
              onTogglePlay={onTogglePlay}
              onLive={onLive}
              onRestart={restartReplay}
            />
          </div>
        ) : null}
      </div>

      {inspectorSlot ? createPortal(inspectorEl, inspectorSlot) : null}
    </div>
  );
}
