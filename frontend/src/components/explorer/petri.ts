// Pure helpers for the Digital Petri Dish view: colour maps for the heat maps, a
// grid→world mapping, and a synthetic single-cell frame used when the user "enters"
// a cell. No React / Three here — unit-tested.

import type { FrameData, HeatmapMetric, PetriCells, PetriSummary } from "../../api/types";

/** World size (scene units) of the square dish plane. */
export const DISH_WORLD = 8;

function hslToRgb(h: number, s: number, l: number): [number, number, number] {
  const k = (n: number) => (n + h * 12) % 12;
  const a = s * Math.min(l, 1 - l);
  const f = (n: number) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
  return [Math.round(f(0) * 255), Math.round(f(8) * 255), Math.round(f(4) * 255)];
}

/** A distinct, stable colour for a clone id (spread around the hue wheel). */
export function cloneColorRGB(clone: number): [number, number, number] {
  if (clone < 0) return [24, 30, 46];
  return hslToRgb((clone * 0.61803) % 1, 0.68, 0.55);
}

const VIRIDIS: [number, number, number][] = [
  [68, 1, 84],
  [59, 82, 139],
  [33, 145, 140],
  [94, 201, 98],
  [253, 231, 37],
];

/** Sample a viridis-like ramp at t in [0,1]. */
export function viridis(t: number): [number, number, number] {
  const x = Math.max(0, Math.min(1, t)) * (VIRIDIS.length - 1);
  const i = Math.floor(x);
  const f = x - i;
  const a = VIRIDIS[i];
  const b = VIRIDIS[Math.min(VIRIDIS.length - 1, i + 1)];
  return [
    Math.round(a[0] + (b[0] - a[0]) * f),
    Math.round(a[1] + (b[1] - a[1]) * f),
    Math.round(a[2] + (b[2] - a[2]) * f),
  ];
}

/**
 * Build an RGBA byte buffer (row-major) for a heat map. For the "clone" metric each
 * cell is coloured by its dominant clone; the others use a viridis ramp normalised to
 * the frame's max, with alpha rising with value.
 */
export function heatmapTexture(
  summary: PetriSummary,
  metric: HeatmapMetric,
): { data: Uint8Array; rows: number; cols: number } {
  const [rows, cols] = summary.hm_size;
  const out = new Uint8Array(rows * cols * 4);

  if (metric === "clone") {
    const map = summary.clone_map;
    for (let i = 0; i < rows * cols; i++) {
      const clone = map[i];
      const [r, g, b] = cloneColorRGB(clone);
      out[i * 4] = r;
      out[i * 4 + 1] = g;
      out[i * 4 + 2] = b;
      out[i * 4 + 3] = clone < 0 ? 40 : 235;
    }
    return { data: out, rows, cols };
  }

  const values = summary.heatmaps[metric];
  const max = Math.max(1e-6, ...values);
  for (let i = 0; i < values.length; i++) {
    const t = values[i] / max;
    const [r, g, b] = viridis(t);
    out[i * 4] = r;
    out[i * 4 + 1] = g;
    out[i * 4 + 2] = b;
    out[i * 4 + 3] = Math.round(30 + 210 * t);
  }
  return { data: out, rows, cols };
}

/** Map a grid coordinate (col x, row y) to a world position on the dish plane. */
export function gridToWorld(x: number, y: number, width: number, height: number): [number, number] {
  const wx = (x / Math.max(1, width - 1) - 0.5) * DISH_WORLD;
  const wy = (0.5 - y / Math.max(1, height - 1)) * DISH_WORLD; // flip: row 0 at top
  return [wx, wy];
}

/**
 * Synthesize a single-cell frame representing one cell in the dish, so the user can
 * "enter" it and see it in the full single-cell Cell Explorer. Values are illustrative
 * but bound to that cell's real energy/mutations and the colony's mean genotype.
 */
export function representativeCellFrame(cells: PetriCells, index: number, summary: PetriSummary): FrameData | null {
  if (index < 0 || index >= cells.count) return null;
  const energy = cells.energy[index];
  const status = energy > 1.5 ? "GROWING" : energy > 0.2 ? "STRESSED" : "DYING";
  const geno = {
    transport: summary.mean_genotype.transport ?? 1,
    membrane: 1,
    replication: 1,
    metabolism: summary.mean_genotype.yield ?? 1,
  };
  return {
    mass: 1.0,
    alive: energy > 0,
    status,
    metabolism_status: energy > 1.5 ? "optimal" : "limited",
    divisions: 0,
    generation: summary.generations,
    lineage: `clone ${cells.clone[index]}`,
    env_glucose: 0,
    pool_glucose: Math.max(0, energy),
    membrane_integrity: Math.max(0.15, Math.min(1, 0.4 + energy * 0.15)),
    genotype: geno,
    phenotype: { ...geno },
    replication: { progress: 0, replicating: false, complete: false },
  };
}
