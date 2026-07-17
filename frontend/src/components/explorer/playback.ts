// Pure helpers for the Cell Explorer timeline: mapping simulation events onto the
// recorded frame history so the user can scrub, pause and replay biological events.
// No React / Three here — unit-tested directly.

import type { Frame, SimEvent } from "../../api/types";

export function clampIndex(i: number, len: number): number {
  if (len <= 0) return 0;
  return Math.max(0, Math.min(len - 1, Math.floor(i)));
}

/** Index of the last frame whose step is <= the given step (0 if none). */
export function frameIndexForStep(frames: Frame[], step: number): number {
  if (frames.length === 0) return 0;
  // Frames are appended in step order, so a linear scan from the end is fine and
  // robust to gaps (frames may be sampled sparsely).
  for (let i = frames.length - 1; i >= 0; i--) {
    if (frames[i].step <= step) return i;
  }
  return 0;
}

export interface EventMarker {
  type: string;
  step: number;
  index: number; // frame index this event lands on
  position: number; // 0..1 along the timeline
}

/** Map each event onto the frame history for timeline markers. */
export function eventMarkers(events: SimEvent[], frames: Frame[]): EventMarker[] {
  if (frames.length === 0) return [];
  const span = Math.max(1, frames.length - 1);
  return events.map((e) => {
    const index = frameIndexForStep(frames, e.step);
    return { type: e.type, step: e.step, index, position: index / span };
  });
}

/** Events whose frame index equals the given index — i.e. "happening now". */
export function activeEvents(markers: EventMarker[], index: number): EventMarker[] {
  return markers.filter((m) => m.index === index);
}

/** Nearest event marker at or after `index` (for a "jump to next event" control). */
export function nextEventIndex(markers: EventMarker[], index: number): number | null {
  let best: number | null = null;
  for (const m of markers) {
    if (m.index > index && (best === null || m.index < best)) best = m.index;
  }
  return best;
}

/** Nearest event marker strictly before `index`. */
export function prevEventIndex(markers: EventMarker[], index: number): number | null {
  let best: number | null = null;
  for (const m of markers) {
    if (m.index < index && (best === null || m.index > best)) best = m.index;
  }
  return best;
}
