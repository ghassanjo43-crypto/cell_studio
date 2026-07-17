import { describe, expect, it } from "vitest";
import type { FrameData } from "../api/types";
import { buildCellVisual, metabolicActivityFrom, radiusForMass } from "../components/explorer/cell/biomap";

function frame(overrides: Partial<FrameData> = {}): FrameData {
  return {
    mass: 1.2,
    alive: true,
    status: "GROWING",
    metabolism_status: "optimal",
    divisions: 1,
    generation: 1,
    lineage: "0",
    env_glucose: 30,
    pool_glucose: 1.5,
    membrane_integrity: 0.9,
    replication: { progress: 0.3, replicating: true, complete: false },
    phenotype: { transport: 1.0, membrane: 1.0, replication: 1.0, metabolism: 1.0 },
    expression: { mrna: 60, protein: 800 },
    ...overrides,
  };
}

describe("biomap: buildCellVisual", () => {
  it("derives radius, integrity and permeability from real fields", () => {
    const v = buildCellVisual(frame({ mass: 1.2, membrane_integrity: 0.7 }), 0.5);
    expect(v.radius).toBeCloseTo(radiusForMass(1.2));
    expect(v.integrity).toBe(0.7);
    expect(v.permeability).toBe(0.7); // permeability tracks integrity
  });

  it("produces data-driven molecular counts for a growing cell", () => {
    const v = buildCellVisual(frame(), 0.8);
    expect(v.glucoseCount).toBeGreaterThan(0); // external glucose present
    expect(v.atpCount).toBeGreaterThan(0); // metabolism active
    expect(v.ribosomeCount).toBeGreaterThan(0); // protein synthesis
    expect(v.metaboliteCount).toBeGreaterThan(0); // internal pool
    expect(v.transcriptionFoci).toBeGreaterThan(0); // mRNA present
    expect(v.transcriptionFoci).toBeLessThanOrEqual(8); // clamped
  });

  it("zeroes molecular traffic when the cell is dead", () => {
    const v = buildCellVisual(frame({ alive: false }), 0);
    expect(v.atpCount).toBe(0);
    expect(v.ribosomeCount).toBe(0);
    expect(v.glucoseCount).toBe(0);
    expect(v.metaboliteCount).toBe(0);
  });

  it("scales transporter activity from the transport phenotype (clamped)", () => {
    expect(buildCellVisual(frame({ phenotype: { transport: 5 } }), 0.5).transportActivity).toBe(2.2);
    expect(buildCellVisual(frame({ phenotype: { transport: 0.01 } }), 0.5).transportActivity).toBe(0.3);
  });

  it("maps the signalling block when present", () => {
    const v = buildCellVisual(
      frame({ signalling: { mode: "SURVIVAL", survival: true, signals: { starvation: 0.8, growth: 0.1, membrane_stress: 0.3 } } }),
      0.2,
    );
    expect(v.signalling?.survival).toBe(true);
    expect(v.signalling?.starvation).toBe(0.8);
  });

  it("boosts ATP with compartment energy pools", () => {
    const withEnergy = buildCellVisual(
      frame({ compartments: { cytosol: { energy: 40, stressed: false } } }),
      0.1,
    );
    const without = buildCellVisual(frame(), 0.1);
    expect(withEnergy.atpCount).toBeGreaterThan(without.atpCount);
  });
});

describe("biomap: metabolicActivityFrom", () => {
  it("is positive when biomass is growing and zero when flat", () => {
    expect(metabolicActivityFrom(1.1, 1.0, 1)).toBeGreaterThan(0);
    expect(metabolicActivityFrom(1.0, 1.0, 1)).toBe(0);
  });

  it("is clamped to [0,1] and safe on bad input", () => {
    expect(metabolicActivityFrom(100, 1, 1)).toBe(1);
    expect(metabolicActivityFrom(1, 1, 0)).toBe(0);
    expect(metabolicActivityFrom(0, 0, 1)).toBe(0);
  });
});
