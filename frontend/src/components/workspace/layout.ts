// Workspace layout persistence + presets. Pure: default layout, (de)serialization to
// localStorage, and named presets. Unit-tested.

import type { QualityMode } from "../explorer/cell/quality";
import type { PresetName } from "./commands";

export type SectionKey = "inspector" | "ai" | "events" | "charts" | "notes";
export type OpenSections = Record<SectionKey, boolean>;

export interface WorkspaceLayout {
  leftCollapsed: boolean;
  rightCollapsed: boolean;
  leftWidth: number;
  dockOpen: boolean;
  quality: QualityMode;
  legend: boolean;
  openSections: OpenSections;
}

export const DEFAULT_LAYOUT: WorkspaceLayout = {
  leftCollapsed: false,
  rightCollapsed: false,
  leftWidth: 280,
  dockOpen: true,
  quality: "high",
  legend: true,
  openSections: { inspector: true, ai: false, events: false, charts: true, notes: false },
};

const KEY = "vcs_workspace_layout";

/** Merge a partial (possibly stale) layout onto the defaults. */
export function mergeLayout(partial: Partial<WorkspaceLayout> | null | undefined): WorkspaceLayout {
  return {
    ...DEFAULT_LAYOUT,
    ...(partial ?? {}),
    openSections: { ...DEFAULT_LAYOUT.openSections, ...(partial?.openSections ?? {}) },
  };
}

export function loadLayout(key = KEY): WorkspaceLayout {
  try {
    const raw = localStorage.getItem(key);
    return mergeLayout(raw ? (JSON.parse(raw) as Partial<WorkspaceLayout>) : null);
  } catch {
    return { ...DEFAULT_LAYOUT };
  }
}

export function saveLayout(layout: WorkspaceLayout, key = KEY): void {
  try {
    localStorage.setItem(key, JSON.stringify(layout));
  } catch {
    /* storage unavailable */
  }
}

export interface PresetResult {
  leftCollapsed: boolean;
  rightCollapsed: boolean;
  dockOpen: boolean;
  legend: boolean;
  quality: QualityMode;
  openSections: OpenSections;
  presentation: boolean;
}

const allClosed: OpenSections = { inspector: false, ai: false, events: false, charts: false, notes: false };

/** The settings a named layout preset applies. */
export function applyPreset(name: PresetName): PresetResult {
  switch (name) {
    case "Research":
      return { leftCollapsed: false, rightCollapsed: false, dockOpen: true, legend: true, quality: "high",
        openSections: { ...allClosed, inspector: true, events: true, charts: true }, presentation: false };
    case "Presentation":
      return { leftCollapsed: true, rightCollapsed: true, dockOpen: false, legend: true, quality: "high",
        openSections: { ...allClosed }, presentation: true };
    case "Teaching":
      return { leftCollapsed: true, rightCollapsed: false, dockOpen: true, legend: true, quality: "medium",
        openSections: { ...allClosed, inspector: true, ai: true, events: true }, presentation: false };
    case "Minimal":
      return { leftCollapsed: true, rightCollapsed: true, dockOpen: false, legend: false, quality: "medium",
        openSections: { ...allClosed }, presentation: false };
    case "VR Prep":
      return { leftCollapsed: true, rightCollapsed: true, dockOpen: false, legend: true, quality: "low",
        openSections: { ...allClosed }, presentation: false };
  }
}
