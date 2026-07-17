import { beforeEach, describe, expect, it, vi } from "vitest";
import { buildCommands, filterCommands, type CommandContext } from "../components/workspace/commands";
import {
  DEFAULT_LAYOUT,
  applyPreset,
  loadLayout,
  mergeLayout,
  saveLayout,
} from "../components/workspace/layout";
import { resolveShortcut, SHORTCUT_COMMANDS } from "../components/workspace/shortcuts";

function ctx(overrides: Partial<CommandContext> = {}): CommandContext {
  const noop = () => {};
  return {
    start: noop, pause: noop, resume: noop, stop: noop,
    canStart: true, canPause: false, canResume: false, canStop: true,
    togglePlay: noop, goLive: noop, restart: noop, resetCamera: noop, enterVR: noop, vrAvailable: false,
    exportFigure: noop, toggleRecord: noop, recording: false, setPresentation: noop, presenting: false,
    toggleLegend: noop, toggleCinematic: noop, cinematic: false, enterInside: noop,
    focus: noop, focusAvailable: () => true, focusSelected: noop,
    toggleInspector: noop, toggleTimeline: noop, openSection: noop, toggleFullscreen: noop, applyPreset: noop,
    ...overrides,
  };
}

describe("command registry", () => {
  it("builds the full command set including focus + presets", () => {
    const ids = buildCommands(ctx()).map((c) => c.id);
    for (const id of ["sim-start", "sim-stop", "go-live", "reset-camera", "enter-vr", "export-figure", "toggle-legend", "toggle-inspector", "toggle-timeline", "fullscreen"]) {
      expect(ids).toContain(id);
    }
    expect(ids).toContain("focus-membrane");
    expect(ids).toContain("focus-genome");
    expect(ids).toContain("preset-presentation");
  });

  it("reflects context enabled-state (VR disabled, resume disabled)", () => {
    const cmds = buildCommands(ctx({ vrAvailable: false, canResume: false }));
    expect(cmds.find((c) => c.id === "enter-vr")!.enabled).toBe(false);
    expect(cmds.find((c) => c.id === "sim-resume")!.enabled).toBe(false);
    expect(buildCommands(ctx({ vrAvailable: true })).find((c) => c.id === "enter-vr")!.enabled).toBe(true);
  });

  it("runs the wired action for a command", () => {
    const reset = vi.fn();
    const focus = vi.fn();
    const cmds = buildCommands(ctx({ resetCamera: reset, focus }));
    cmds.find((c) => c.id === "reset-camera")!.run();
    expect(reset).toHaveBeenCalledOnce();
    cmds.find((c) => c.id === "focus-genome")!.run();
    expect(focus).toHaveBeenCalledWith("genome");
  });

  it("offers a replay command that re-runs the animation", () => {
    const restart = vi.fn();
    const cmds = buildCommands(ctx({ restart }));
    const replay = cmds.find((c) => c.id === "replay")!;
    expect(replay).toBeTruthy();
    expect(replay.enabled).toBe(true);
    replay.run();
    expect(restart).toHaveBeenCalledOnce();
    // Discoverable by "restart" / "re-run" search.
    expect(filterCommands(cmds, "restart").some((c) => c.id === "replay")).toBe(true);
  });

  it("presentation command toggles based on state", () => {
    const setPresentation = vi.fn();
    buildCommands(ctx({ presenting: false, setPresentation })).find((c) => c.id === "presentation")!.run();
    expect(setPresentation).toHaveBeenCalledWith(true);
    buildCommands(ctx({ presenting: true, setPresentation })).find((c) => c.id === "presentation")!.run();
    expect(setPresentation).toHaveBeenCalledWith(false);
  });

  it("filters and ranks by query", () => {
    const cmds = buildCommands(ctx());
    expect(filterCommands(cmds, "").length).toBe(cmds.length);
    const focus = filterCommands(cmds, "focus").map((c) => c.id);
    expect(focus).toContain("focus-membrane");
    expect(focus.every((id) => id.includes("focus"))).toBe(true);
    // Title-prefix ranks first.
    const live = filterCommands(cmds, "go live");
    expect(live[0].id).toBe("go-live");
  });
});

describe("shortcut resolution", () => {
  const ev = (key: string, opts: Partial<KeyboardEvent> & { tag?: string } = {}) =>
    ({ key, metaKey: opts.metaKey, ctrlKey: opts.ctrlKey, target: opts.tag ? { tagName: opts.tag } : undefined }) as never;

  it("resolves plain shortcuts", () => {
    expect(resolveShortcut(ev(" "))).toBe("space");
    expect(resolveShortcut(ev("L"))).toBe("l");
    expect(resolveShortcut(ev("f"))).toBe("f");
    expect(resolveShortcut(ev("x"))).toBeNull();
  });

  it("resolves the command-palette and escape globally", () => {
    expect(resolveShortcut(ev("k", { metaKey: true }))).toBe("mod+k");
    expect(resolveShortcut(ev("k", { ctrlKey: true }))).toBe("mod+k");
    expect(resolveShortcut(ev("Escape"))).toBe("escape");
  });

  it("ignores plain keys while typing, but not palette/escape", () => {
    expect(resolveShortcut(ev("g", { tag: "INPUT" }))).toBeNull();
    expect(resolveShortcut(ev(" ", { tag: "TEXTAREA" }))).toBeNull();
    expect(resolveShortcut(ev("k", { metaKey: true, tag: "INPUT" }))).toBe("mod+k");
    expect(resolveShortcut(ev("Escape", { tag: "TEXTAREA" }))).toBe("escape");
  });

  it("maps plain shortcuts to command ids", () => {
    expect(SHORTCUT_COMMANDS["l"]).toBe("go-live");
    expect(SHORTCUT_COMMANDS["t"]).toBe("toggle-timeline");
    expect(SHORTCUT_COMMANDS["0"]).toBe("replay");
  });

  it("resolves the replay shortcut (0)", () => {
    expect(resolveShortcut(ev("0"))).toBe("0");
    expect(resolveShortcut(ev("0", { tag: "INPUT" }))).toBeNull(); // ignored while typing
  });
});

describe("layout persistence + presets", () => {
  beforeEach(() => localStorage.clear());

  it("merges partial layouts onto defaults (incl. nested sections)", () => {
    const merged = mergeLayout({ leftCollapsed: true, openSections: { ai: true } as never });
    expect(merged.leftCollapsed).toBe(true);
    expect(merged.leftWidth).toBe(DEFAULT_LAYOUT.leftWidth);
    expect(merged.openSections.ai).toBe(true);
    expect(merged.openSections.inspector).toBe(DEFAULT_LAYOUT.openSections.inspector);
  });

  it("round-trips through localStorage", () => {
    const custom = { ...DEFAULT_LAYOUT, leftWidth: 360, quality: "low" as const, legend: false };
    saveLayout(custom);
    expect(loadLayout()).toEqual(custom);
  });

  it("returns defaults when nothing is stored or storage is bad", () => {
    expect(loadLayout()).toEqual(DEFAULT_LAYOUT);
    localStorage.setItem("vcs_workspace_layout", "not json");
    expect(loadLayout()).toEqual(DEFAULT_LAYOUT);
  });

  it("applies presets that reshape the workspace", () => {
    const present = applyPreset("Presentation");
    expect(present).toMatchObject({ leftCollapsed: true, rightCollapsed: true, dockOpen: false, presentation: true });

    const research = applyPreset("Research");
    expect(research.presentation).toBe(false);
    expect(research.openSections.charts).toBe(true);
    expect(research.rightCollapsed).toBe(false);

    expect(applyPreset("VR Prep").quality).toBe("low");
    expect(applyPreset("Minimal").legend).toBe(false);
  });
});
