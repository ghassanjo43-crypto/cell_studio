import { describe, expect, it } from "vitest";
import type { FrameData } from "../api/types";
import { buildCellVisual } from "../components/explorer/cell/biomap";
import { calloutTargets } from "../components/explorer/cell/callouts";

function frame(overrides: Partial<FrameData> = {}): FrameData {
  return {
    mass: 1.2, alive: true, status: "GROWING", metabolism_status: "optimal",
    divisions: 0, generation: 0, lineage: "0", env_glucose: 20, pool_glucose: 1.2,
    membrane_integrity: 0.9,
    replication: { progress: 0.2, replicating: true, complete: false },
    phenotype: { transport: 1, membrane: 1, replication: 1, metabolism: 1 },
    expression: { mrna: 40, protein: 900 },
    ...overrides,
  };
}

describe("cinematic: crowding + protein density (data-driven)", () => {
  it("derives macromolecular crowding + protein counts from biomass/expression", () => {
    const v = buildCellVisual(frame(), 0.6);
    expect(v.crowdingCount).toBeGreaterThan(0);
    expect(v.proteinCount).toBeGreaterThan(0);
  });

  it("zeroes crowding + proteins when the cell is dead", () => {
    const v = buildCellVisual(frame({ alive: false }), 0);
    expect(v.crowdingCount).toBe(0);
    expect(v.proteinCount).toBe(0);
  });

  it("crowding rises with biomass", () => {
    const small = buildCellVisual(frame({ mass: 0.3 }), 0.5).crowdingCount;
    const big = buildCellVisual(frame({ mass: 2.0 }), 0.5).crowdingCount;
    expect(big).toBeGreaterThanOrEqual(small);
  });
});

describe("cinematic: callout labels (only for present structures)", () => {
  it("labels the core single-cell structures", () => {
    const ids = calloutTargets(frame()).map((c) => c.id);
    for (const id of ["membrane", "transport", "channel", "ribosome", "nucleoid", "cytoplasm", "atp"]) {
      expect(ids).toContain(id);
    }
    expect(ids).not.toContain("signalling");
    expect(ids).not.toContain("nutrients");
  });

  it("adds signalling + nutrient labels only when that data exists", () => {
    const sig = calloutTargets(frame({ signalling: { mode: "SURVIVAL", survival: true, signals: { starvation: 0.8, growth: 0.1, membrane_stress: 0.2 } } }));
    expect(sig.some((c) => c.id === "signalling")).toBe(true);
    const nut = calloutTargets(frame({ field_glc: [1, 2, 3] }));
    expect(nut.some((c) => c.id === "nutrients")).toBe(true);
  });

  it("every callout has a label and a 3D anchor", () => {
    for (const c of calloutTargets(frame())) {
      expect(c.label.length).toBeGreaterThan(0);
      expect(c.anchor).toHaveLength(3);
    }
  });
});
