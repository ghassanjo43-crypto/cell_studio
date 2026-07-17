// Keyboard-shortcut resolution. Pure: turn a KeyboardEvent into a canonical shortcut
// key (or null). The workspace maps that key to an action. Typing in a form field is
// ignored, except the global command-palette / escape shortcuts. Unit-tested.

export type ShortcutKey =
  | "space" | "l" | "f" | "r" | "v" | "g" | "i" | "t" | "0" | "mod+k" | "escape";

const PLAIN: ShortcutKey[] = ["space", "l", "f", "r", "v", "g", "i", "t", "0"];

interface KeyLike {
  key: string;
  metaKey?: boolean;
  ctrlKey?: boolean;
  target?: unknown;
}

function isEditable(target: unknown): boolean {
  const el = target as { tagName?: string; isContentEditable?: boolean } | null;
  if (!el) return false;
  const tag = (el.tagName ?? "").toUpperCase();
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable === true;
}

/** Canonical shortcut for an event, or null if it isn't one (or should be ignored). */
export function resolveShortcut(e: KeyLike): ShortcutKey | null {
  const mod = e.metaKey || e.ctrlKey;
  // These work even while typing in a field.
  if (mod && e.key.toLowerCase() === "k") return "mod+k";
  if (e.key === "Escape") return "escape";
  if (isEditable(e.target)) return null;
  if (mod) return null; // don't hijack other Ctrl/Cmd combos
  const k = e.key === " " ? "space" : e.key.toLowerCase();
  return (PLAIN as string[]).includes(k) ? (k as ShortcutKey) : null;
}

/** The command id a plain shortcut maps to (mod+k / escape handled separately). */
export const SHORTCUT_COMMANDS: Record<string, string> = {
  space: "toggle-play",
  l: "go-live",
  f: "focus-selected",
  r: "reset-camera",
  v: "enter-vr",
  g: "toggle-legend",
  i: "toggle-inspector",
  t: "toggle-timeline",
  "0": "replay",
};
