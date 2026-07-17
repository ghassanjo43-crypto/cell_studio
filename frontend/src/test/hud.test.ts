import { describe, expect, it } from "vitest";
import type { FrameData, PetriSummary } from "../api/types";
import { focusPresets } from "../components/explorer/focus";
import { legendItems } from "../components/explorer/legendItems";

function singleCell(overrides: Partial<FrameData> = {}): FrameData {
  return {
    mass: 1, alive: true, status: "GROWING", metabolism_status: "optimal",
    divisions: 0, generation: 0, lineage: "0", env_glucose: 20, pool_glucose: 1,
    membrane_integrity: 0.9, ...overrides,
  };
}

function petriFrame(): FrameData {
  const petri: PetriSummary = {
    step: 10, alive: 5, dead: 0, born: 5, died: 0, colonies: 3, n_clones: 3,
    dominant_clone: 1, dominant_fraction: 0.5, generations: 1, occupancy: 0.2,
    total_nutrient: 100, mean_genotype: { transport: 1, yield: 1 }, grid: [4, 4], hm_size: [2, 2],
    heatmaps: { population: [1, 0, 0, 0], nutrient: [1, 1, 0, 0], mutation: [0, 0, 0, 0], atp: [0, 0, 0, 0] },
    clone_map: [0, 1, -1, -1],
    cells: { x: [], y: [], clone: [], energy: [], mut: [], count: 0, cap: 4000 },
  };
  return { ...(singleCell() as FrameData), petri };
}

describe("scene legend", () => {
  it("lists the single-cell structures with membrane status colour", () => {
    const items = legendItems(singleCell(), "clone");
    const labels = items.map((i) => i.label);
    expect(labels).toContain("transporters");
    expect(labels).toContain("genome");
    expect(labels).toContain("ATP");
    expect(labels.some((l) => l.startsWith("membrane"))).toBe(true);
  });

  it("adds signalling/compartments entries only when present", () => {
    const plain = legendItems(singleCell(), "clone").map((i) => i.label);
    expect(plain.some((l) => l.includes("signalling"))).toBe(false);
    const withSig = legendItems(
      singleCell({ signalling: { mode: "NORMAL", survival: false, signals: { starvation: 0, growth: 1, membrane_stress: 0 } } }),
      "clone",
    ).map((i) => i.label);
    expect(withSig.some((l) => l.includes("signalling"))).toBe(true);
  });

  it("shows clone colours + a floor-metric note for the dish", () => {
    const items = legendItems(petriFrame(), "nutrient");
    expect(items.some((i) => i.label === "clone #0")).toBe(true);
    expect(items.some((i) => i.label.includes("floor = nutrient"))).toBe(true);
    expect(items.some((i) => i.label.includes("ATP"))).toBe(true);
  });
});

describe("focus presets", () => {
  it("offers cell structures for a single cell, gated by scenario", () => {
    const base = focusPresets(singleCell()).map((f) => f.key);
    expect(base).toEqual(["membrane", "genome", "metabolism"]);
    const rich = focusPresets(
      singleCell({
        signalling: { mode: "NORMAL", survival: false, signals: { starvation: 0, growth: 1, membrane_stress: 0 } },
        field_glc: [1, 2, 3],
      }),
    ).map((f) => f.key);
    expect(rich).toContain("signalling");
    expect(rich).toContain("nutrients");
  });

  it("offers colony/nutrients for the dish, selecting the dish object", () => {
    const presets = focusPresets(petriFrame());
    expect(presets.map((f) => f.key)).toEqual(["colony", "nutrients"]);
    expect(presets[0].id).toBe("petri");
  });

  it("returns nothing without a frame", () => {
    expect(focusPresets(null)).toEqual([]);
    expect(legendItems(null, "clone")).toEqual([]);
  });
});
