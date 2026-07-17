// The command registry — the single list of actions the command palette and the
// keyboard shortcuts dispatch to. Pure: `buildCommands` maps a context of callbacks
// to Command objects, and `filterCommands` searches them. Unit-tested.

import type { FocusKey } from "../explorer/focus";

export interface Command {
  id: string;
  title: string;
  group: string;
  keywords?: string;
  shortcut?: string;
  run: () => void;
  enabled: boolean;
}

export type PresetName = "Research" | "Presentation" | "Teaching" | "Minimal" | "VR Prep";

export interface CommandContext {
  // Simulation (worker) controls.
  start: () => void;
  pause: () => void;
  resume: () => void;
  stop: () => void;
  canStart: boolean;
  canPause: boolean;
  canResume: boolean;
  canStop: boolean;
  // Playback / camera / viewer (CellExplorer imperative API).
  togglePlay: () => void;
  goLive: () => void;
  restart: () => void;
  resetCamera: () => void;
  enterVR: () => void;
  vrAvailable: boolean;
  exportFigure: () => void;
  toggleRecord: () => void;
  recording: boolean;
  setPresentation: (on: boolean) => void;
  presenting: boolean;
  toggleLegend: () => void;
  toggleCinematic: () => void;
  cinematic: boolean;
  enterInside: () => void;
  focus: (key: FocusKey) => void;
  focusAvailable: (key: FocusKey) => boolean;
  focusSelected: () => void;
  // Workspace panels.
  toggleInspector: () => void;
  toggleTimeline: () => void;
  openSection: (key: "ai" | "events" | "charts" | "notes") => void;
  toggleFullscreen: () => void;
  applyPreset: (name: PresetName) => void;
}

const FOCI: { key: FocusKey; label: string }[] = [
  { key: "membrane", label: "Membrane" },
  { key: "genome", label: "Genome" },
  { key: "metabolism", label: "Metabolism" },
  { key: "signalling", label: "Signalling" },
  { key: "nutrients", label: "Nutrients" },
];

const PRESETS: PresetName[] = ["Research", "Presentation", "Teaching", "Minimal", "VR Prep"];

export function buildCommands(ctx: CommandContext): Command[] {
  const cmds: Command[] = [
    { id: "sim-start", title: "Start simulation", group: "Simulation", keywords: "run play begin", run: ctx.start, enabled: ctx.canStart },
    { id: "sim-pause", title: "Pause", group: "Simulation", run: ctx.pause, enabled: ctx.canPause },
    { id: "sim-resume", title: "Resume", group: "Simulation", run: ctx.resume, enabled: ctx.canResume },
    { id: "sim-stop", title: "Stop", group: "Simulation", keywords: "halt end", run: ctx.stop, enabled: ctx.canStop },
    { id: "go-live", title: "Go live", group: "Playback", keywords: "follow latest", shortcut: "L", run: ctx.goLive, enabled: true },
    { id: "toggle-play", title: "Play / pause replay", group: "Playback", shortcut: "Space", run: ctx.togglePlay, enabled: true },
    { id: "replay", title: "Replay animation", group: "Playback", keywords: "restart rerun re-run start over stop and replay", shortcut: "0", run: ctx.restart, enabled: true },
    { id: "reset-camera", title: "Reset camera", group: "Camera", keywords: "home view", shortcut: "R", run: ctx.resetCamera, enabled: true },
    { id: "focus-selected", title: "Focus selected structure", group: "Camera", shortcut: "F", run: ctx.focusSelected, enabled: true },
    { id: "enter-vr", title: "Enter VR", group: "View", keywords: "immersive headset", shortcut: "V", run: ctx.enterVR, enabled: ctx.vrAvailable },
    { id: "export-figure", title: "Export figure", group: "View", keywords: "screenshot png image", run: ctx.exportFigure, enabled: true },
    { id: "toggle-record", title: ctx.recording ? "Stop recording" : "Start recording", group: "View", keywords: "movie video webm capture", run: ctx.toggleRecord, enabled: true },
    { id: "presentation", title: ctx.presenting ? "Stop presentation" : "Presentation mode", group: "View", keywords: "tour present", run: () => ctx.setPresentation(!ctx.presenting), enabled: true },
    { id: "cinematic", title: ctx.cinematic ? "Exit cinematic mode" : "Cinematic mode", group: "View", keywords: "immersive molecular environment", run: ctx.toggleCinematic, enabled: true },
    { id: "inside-cell", title: "Inside cell view", group: "Camera", keywords: "cytoplasm interior fly in", run: ctx.enterInside, enabled: true },
    { id: "toggle-legend", title: "Toggle legend", group: "Panels", shortcut: "G", run: ctx.toggleLegend, enabled: true },
    { id: "toggle-inspector", title: "Toggle inspector", group: "Panels", shortcut: "I", run: ctx.toggleInspector, enabled: true },
    { id: "toggle-timeline", title: "Toggle timeline dock", group: "Panels", shortcut: "T", run: ctx.toggleTimeline, enabled: true },
    { id: "open-ai", title: "Open AI Copilot", group: "Panels", keywords: "assistant chat", run: () => ctx.openSection("ai"), enabled: true },
    { id: "open-events", title: "Open lifecycle events", group: "Panels", run: () => ctx.openSection("events"), enabled: true },
    { id: "open-charts", title: "Open charts", group: "Panels", keywords: "graphs plots", run: () => ctx.openSection("charts"), enabled: true },
    { id: "open-notes", title: "Open scientific notes", group: "Panels", run: () => ctx.openSection("notes"), enabled: true },
    { id: "fullscreen", title: "Full screen", group: "View", keywords: "maximize expand", run: ctx.toggleFullscreen, enabled: true },
  ];

  for (const f of FOCI) {
    cmds.push({
      id: `focus-${f.key}`,
      title: `Focus ${f.label}`,
      group: "Camera",
      keywords: "zoom to structure",
      run: () => ctx.focus(f.key),
      enabled: ctx.focusAvailable(f.key),
    });
  }

  for (const p of PRESETS) {
    cmds.push({
      id: `preset-${p.toLowerCase().replace(/\s+/g, "-")}`,
      title: `Layout: ${p}`,
      group: "Presets",
      keywords: "workspace layout preset",
      run: () => ctx.applyPreset(p),
      enabled: true,
    });
  }

  return cmds;
}

/** Filter + rank commands by a search query (empty → all). */
export function filterCommands(commands: Command[], query: string): Command[] {
  const q = query.trim().toLowerCase();
  if (!q) return commands;
  const scored = commands
    .map((c) => {
      const hay = `${c.title} ${c.group} ${c.keywords ?? ""}`.toLowerCase();
      if (!hay.includes(q)) return null;
      // Rank: title prefix > title contains > other.
      const t = c.title.toLowerCase();
      const score = t.startsWith(q) ? 0 : t.includes(q) ? 1 : 2;
      return { c, score };
    })
    .filter((x): x is { c: Command; score: number } => x !== null)
    .sort((a, b) => a.score - b.score);
  return scored.map((s) => s.c);
}
