// Pure helpers for the colony view: a deterministic phyllotaxis layout of cells and
// a stable colour per clone (lineage root). No React / Three — unit-tested.

import type { PopulationCell } from "../../api/types";

const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));

/** Deterministic 2D position for the i-th cell in a sunflower packing. */
export function colonyPosition(i: number, spacing = 0.42): [number, number] {
  const r = spacing * Math.sqrt(i);
  const theta = i * GOLDEN_ANGLE;
  return [Math.cos(theta) * r, Math.sin(theta) * r];
}

/** Visual radius of a cell from its biomass (cbrt, clamped to a sensible range). */
export function cellRadius(mass: number): number {
  return Math.min(0.42, 0.12 + Math.cbrt(Math.max(mass, 0)) * 0.16);
}

/** A stable hue [0,1) hashed from a clone's lineage root. */
export function lineageHue(root: string): number {
  let h = 0;
  for (let i = 0; i < root.length; i++) h = (h * 31 + root.charCodeAt(i)) >>> 0;
  return (h % 360) / 360;
}

/** `hsl(...)` colour string for a clone, dimmed when the cell is dead. */
export function lineageColor(root: string, alive: boolean): string {
  const hue = Math.round(lineageHue(root) * 360);
  return alive ? `hsl(${hue}, 70%, 55%)` : `hsl(${hue}, 12%, 32%)`;
}

/** Group living cells by clone root, largest first — for a lineage legend. */
export function cloneCounts(cells: PopulationCell[]): { root: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const c of cells) {
    if (!c.alive) continue;
    counts.set(c.root, (counts.get(c.root) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([root, count]) => ({ root, count }))
    .sort((a, b) => b.count - a.count);
}
