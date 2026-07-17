import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { simulationsApi } from "../api/endpoints";
import type { Simulation, SimulationStatus } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { AiCopilot } from "../components/AiCopilot";
import { CellExplorer, type CellExplorerApi, type ViewerState } from "../components/explorer/CellExplorer";
import { Dashboard } from "../components/Dashboard";
import { EventTimeline } from "../components/EventTimeline";
import { DrugStudioPanel } from "../components/pharmacology/DrugStudioPanel";
import { DrugStoryboard } from "../components/pharmacology/DrugStoryboard";
import type { DrugDose } from "../api/types";
import { buildCommands, type Command, type CommandContext, type PresetName } from "../components/workspace/commands";
import { CommandPalette } from "../components/workspace/CommandPalette";
import { applyPreset, loadLayout, saveLayout, type OpenSections, type SectionKey } from "../components/workspace/layout";
import { OnboardingTips } from "../components/workspace/OnboardingTips";
import { ScientificNotes } from "../components/workspace/ScientificNotes";
import { resolveShortcut, SHORTCUT_COMMANDS } from "../components/workspace/shortcuts";
import { SidebarSection } from "../components/workspace/SidebarSection";
import { useSimulationStream } from "../stream/useSimulationStream";

const TERMINAL: SimulationStatus[] = ["DONE", "STOPPED", "FAILED"];
const MIN_LEFT = 200;
const MAX_LEFT = 420;
const PRESETS: PresetName[] = ["Research", "Presentation", "Teaching", "Minimal", "VR Prep"];

function SimulationView({ simId }: { simId: number }) {
  const { token } = useAuth();
  const navigate = useNavigate();
  const [sim, setSim] = useState<Simulation | null>(null);
  const [busy, setBusy] = useState(false);

  const [layout0] = useState(() => loadLayout());
  const [leftCollapsed, setLeftCollapsed] = useState(layout0.leftCollapsed);
  const [rightCollapsed, setRightCollapsed] = useState(layout0.rightCollapsed);
  const [leftWidth, setLeftWidth] = useState(layout0.leftWidth);
  const [openSections, setOpenSections] = useState<OpenSections>(layout0.openSections);
  const [fullscreen, setFullscreen] = useState(false);
  const [inspectorSlot, setInspectorSlot] = useState<HTMLElement | null>(null);
  const [viewerState, setViewerState] = useState<ViewerState | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [regimen, setRegimen] = useState<DrugDose[]>([]);
  const [onboard, setOnboard] = useState(() => {
    try {
      return !localStorage.getItem("vcs_onboarded");
    } catch {
      return false;
    }
  });

  const workspaceRef = useRef<HTMLDivElement>(null);
  const cellApiRef = useRef<CellExplorerApi | null>(null);
  const commandsRef = useRef<Command[]>([]);
  const paletteRef = useRef(false);
  const onboardRef = useRef(false);
  paletteRef.current = paletteOpen;
  onboardRef.current = onboard;

  const refresh = useCallback(async () => {
    setSim(await simulationsApi.get(simId));
  }, [simId]);
  useEffect(() => {
    refresh();
  }, [refresh]);
  useEffect(() => {
    if (!sim || TERMINAL.includes(sim.status)) return;
    const t = setInterval(refresh, 1500);
    return () => clearInterval(t);
  }, [sim, refresh]);

  const stream = useSimulationStream(simId, token, true);
  // Prefer the LIVE status from the WebSocket stream (it updates to RUNNING/DONE/… as the
  // worker progresses); fall back to the initially-fetched row, then CREATED. Using it only
  // when `stream.done` (the old behaviour) left the UI stuck on the stale QUEUED/CREATED row
  // while the run was actually RUNNING — which hid the live drug-injection controls.
  const status: SimulationStatus = stream.status ?? sim?.status ?? "CREATED";

  async function act(fn: () => Promise<Simulation>) {
    setBusy(true);
    try {
      setSim(await fn());
    } finally {
      setBusy(false);
    }
  }

  // Full screen (Esc exits; rails collapse while in it).
  useEffect(() => {
    const onChange = () => {
      const fs = document.fullscreenElement === workspaceRef.current;
      setFullscreen(fs);
      if (fs) {
        setLeftCollapsed(true);
        setRightCollapsed(true);
      }
    };
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);
  function toggleFullscreen() {
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    else workspaceRef.current?.requestFullscreen().catch(() => {});
  }

  useEffect(() => {
    const header = document.querySelector(".app-header") as HTMLElement | null;
    workspaceRef.current?.style.setProperty("--ws-top", `${header?.offsetHeight ?? 56}px`);
  }, []);

  // Persist layout preferences (keyed on primitives so it saves only on real change).
  useEffect(() => {
    if (!viewerState) return;
    saveLayout({
      leftCollapsed, rightCollapsed, leftWidth,
      dockOpen: viewerState.dock, quality: viewerState.quality, legend: viewerState.legend, openSections,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leftCollapsed, rightCollapsed, leftWidth, openSections, viewerState?.dock, viewerState?.quality, viewerState?.legend]);

  const closeOnboard = useCallback(() => {
    setOnboard(false);
    try {
      localStorage.setItem("vcs_onboarded", "1");
    } catch {
      /* ignore */
    }
  }, []);

  // Section helpers.
  const toggleSection = (key: SectionKey) => setOpenSections((s) => ({ ...s, [key]: !s[key] }));
  const openSection = (key: SectionKey) => {
    setRightCollapsed(false);
    setOpenSections((s) => ({ ...s, [key]: true }));
  };

  function applyPresetLocal(name: PresetName) {
    const p = applyPreset(name);
    setLeftCollapsed(p.leftCollapsed);
    setRightCollapsed(p.rightCollapsed);
    setOpenSections(p.openSections);
    const api = cellApiRef.current;
    api?.setDock(p.dockOpen);
    api?.setLegend(p.legend);
    api?.setQuality(p.quality);
    api?.setPresentation(p.presentation);
  }

  // Left resizer.
  function startResize(e: React.MouseEvent) {
    e.preventDefault();
    const move = (ev: MouseEvent) => {
      const rect = workspaceRef.current?.getBoundingClientRect();
      const x = rect ? ev.clientX - rect.left : ev.clientX;
      setLeftWidth(Math.max(MIN_LEFT, Math.min(MAX_LEFT, x)));
    };
    const up = () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  }

  // Command registry (rebuilt each render; refs used at run time keep it fresh).
  const canStart = status === "CREATED" || status === "STOPPED";
  const ctx: CommandContext = {
    start: () => act(() => simulationsApi.start(simId)),
    pause: () => act(() => simulationsApi.pause(simId)),
    resume: () => act(() => simulationsApi.resume(simId)),
    stop: () => act(() => simulationsApi.stop(simId)),
    canStart,
    canPause: status === "RUNNING" || status === "QUEUED",
    canResume: status === "PAUSED",
    canStop: !["DONE", "STOPPED", "FAILED"].includes(status),
    togglePlay: () => cellApiRef.current?.togglePlay(),
    goLive: () => cellApiRef.current?.goLive(),
    restart: () => cellApiRef.current?.restart(),
    resetCamera: () => cellApiRef.current?.resetCamera(),
    enterVR: () => cellApiRef.current?.enterVR(),
    vrAvailable: viewerState?.vrAvailable ?? false,
    exportFigure: () => cellApiRef.current?.exportFigure(),
    toggleRecord: () => cellApiRef.current?.toggleRecord(),
    recording: viewerState?.recording ?? false,
    setPresentation: (on) => cellApiRef.current?.setPresentation(on),
    presenting: viewerState?.presenting ?? false,
    toggleLegend: () => cellApiRef.current?.toggleLegend(),
    toggleCinematic: () => cellApiRef.current?.toggleCinematic(),
    cinematic: viewerState?.cinematic ?? false,
    enterInside: () => cellApiRef.current?.enterInside(),
    focus: (key) => cellApiRef.current?.focus(key),
    focusAvailable: (key) => viewerState?.focusKeys.includes(key) ?? false,
    focusSelected: () => cellApiRef.current?.focusSelected(),
    toggleInspector: () => {
      setRightCollapsed(false);
      toggleSection("inspector");
    },
    toggleTimeline: () => cellApiRef.current?.toggleTimeline(),
    openSection,
    toggleFullscreen,
    applyPreset: applyPresetLocal,
  };
  const commands = buildCommands(ctx);
  commandsRef.current = commands;

  // Global keyboard shortcuts.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const key = resolveShortcut(e);
      if (!key) return;
      if (key === "mod+k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
        return;
      }
      if (key === "escape") {
        if (paletteRef.current) {
          setPaletteOpen(false);
          e.preventDefault();
        } else if (onboardRef.current) {
          closeOnboard();
          e.preventDefault();
        } else {
          cellApiRef.current?.closeSettings();
        }
        return;
      }
      const id = SHORTCUT_COMMANDS[key];
      const cmd = commandsRef.current.find((c) => c.id === id);
      if (cmd && cmd.enabled) {
        e.preventDefault();
        cmd.run();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [closeOnboard]);

  const scenario = stream.frames.length
    ? stream.frames[stream.frames.length - 1].data.petri
      ? "petri"
      : stream.frames[stream.frames.length - 1].data.population
      ? "population"
      : "single cell"
    : "—";

  return (
    <div
      ref={workspaceRef}
      className={`workspace ${fullscreen ? "is-fullscreen" : ""} ${leftCollapsed ? "left-collapsed" : ""} ${rightCollapsed ? "right-collapsed" : ""}`}
    >
      {/* LEFT: metrics + layout */}
      <aside className="ws-left" style={{ width: leftCollapsed ? 44 : leftWidth }}>
        <div className="rail-head">
          <button className="rail-toggle" onClick={() => setLeftCollapsed((c) => !c)} title="Metrics panel">
            {leftCollapsed ? "📊" : "◂"}
          </button>
          {!leftCollapsed ? <span className="rail-title">Metrics</span> : null}
        </div>
        {!leftCollapsed ? (
          <div className="rail-body">
            <SidebarSection title="Layout" icon="🎛️" defaultOpen>
              <div className="preset-bar">
                {PRESETS.map((p) => (
                  <button key={p} className="btn btn-small" onClick={() => applyPresetLocal(p)} title={`${p} layout preset`}>
                    {p}
                  </button>
                ))}
              </div>
            </SidebarSection>
            <SidebarSection title="Run" icon="🧫" defaultOpen>
              <div className="run-info">
                <div><span>Simulation</span><b>#{simId}</b></div>
                <div><span>Scenario</span><b>{scenario}</b></div>
                <div><span>Status</span><b className={`status-${status.toLowerCase()}`}>{status}</b></div>
                <div><span>Step</span><b>{sim?.current_step ?? 0}</b></div>
                {sim?.outcome ? <div><span>Outcome</span><b>{sim.outcome}</b></div> : null}
              </div>
            </SidebarSection>
            <SidebarSection title="Metrics" icon="📊" defaultOpen>
              <Dashboard frames={stream.frames} variant="metrics" />
            </SidebarSection>
          </div>
        ) : null}
        {!leftCollapsed ? <div className="rail-resizer" onMouseDown={startResize} /> : null}
      </aside>

      {/* CENTER: immersive Cell Explorer */}
      <section className="ws-center">
        <div className="ws-topbar">
          <button className="btn btn-small" onClick={() => navigate(-1)}>← Back</button>
          <button className="btn btn-small" onClick={() => setPaletteOpen(true)} title="Command palette">⌘K</button>
          <button className="btn btn-small" onClick={() => setOnboard(true)} title="Workspace tips">？</button>
        </div>
        <CellExplorer
          frames={stream.frames}
          events={stream.events}
          connected={stream.connected}
          title={`Virtual Cell Studio — Simulation #${simId}`}
          sim={{
            status, busy,
            onStart: () => act(() => simulationsApi.start(simId)),
            onPause: () => act(() => simulationsApi.pause(simId)),
            onResume: () => act(() => simulationsApi.resume(simId)),
            onStop: () => act(() => simulationsApi.stop(simId)),
          }}
          inspectorSlot={inspectorSlot}
          fullscreen={fullscreen}
          onToggleFullscreen={toggleFullscreen}
          apiRef={cellApiRef}
          onViewerState={setViewerState}
          initialQuality={layout0.quality}
          initialLegend={layout0.legend}
          initialDock={layout0.dockOpen}
        />
      </section>

      {/* RIGHT: analysis accordion */}
      <aside className={`ws-right ${rightCollapsed ? "is-collapsed" : ""}`}>
        <div className="rail-head">
          <button className="rail-toggle" onClick={() => setRightCollapsed((c) => !c)} title="Analysis panel">
            {rightCollapsed ? "🔬" : "▸"}
          </button>
          {!rightCollapsed ? <span className="rail-title">Analysis</span> : null}
        </div>
        <div className="rail-body">
          <SidebarSection title="Inspector" icon="🔬" keepMounted open={openSections.inspector} onToggle={() => toggleSection("inspector")}>
            <div ref={setInspectorSlot} className="inspector-slot" />
          </SidebarSection>
          {!rightCollapsed ? (
            <>
              <SidebarSection title="Drug Studio" icon="💊" defaultOpen>
                <DrugStudioPanel
                  regimen={regimen}
                  onRegimenChange={setRegimen}
                  simId={simId}
                  status={status}
                  running={status === "RUNNING"}
                  frame={stream.frames.length ? stream.frames[stream.frames.length - 1].data : null}
                  baselineFrame={stream.frames.length ? stream.frames[0].data : null}
                />
              </SidebarSection>
              <SidebarSection title="Drug Response" icon="🎬" defaultOpen>
                <DrugStoryboard
                  frame={stream.frames.length ? stream.frames[stream.frames.length - 1].data : null}
                  history={stream.frames.map((f) => f.data)}
                />
              </SidebarSection>
              <SidebarSection title="AI Copilot" icon="◈" open={openSections.ai} onToggle={() => toggleSection("ai")}>
                <AiCopilot simId={simId} disabled={sim === null} />
              </SidebarSection>
              <SidebarSection title="Lifecycle Events" icon="⧗" open={openSections.events} onToggle={() => toggleSection("events")}>
                <EventTimeline events={stream.events} />
              </SidebarSection>
              <SidebarSection title="Charts" icon="📈" open={openSections.charts} onToggle={() => toggleSection("charts")}>
                <Dashboard frames={stream.frames} variant="charts" />
              </SidebarSection>
              <SidebarSection title="Scientific Notes" icon="📝" open={openSections.notes} onToggle={() => toggleSection("notes")}>
                <ScientificNotes simId={simId} />
              </SidebarSection>
            </>
          ) : null}
        </div>
      </aside>

      {paletteOpen ? <CommandPalette commands={commands} onClose={() => setPaletteOpen(false)} /> : null}
      {onboard ? <OnboardingTips onClose={closeOnboard} /> : null}
    </div>
  );
}

export function SimulationPage() {
  const { simId } = useParams();
  const id = Number(simId);
  return <SimulationView key={id} simId={id} />;
}
