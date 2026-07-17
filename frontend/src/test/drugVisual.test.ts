import { describe, expect, it } from "vitest";
import type { ActiveDrug, FrameData } from "../api/types";
import { buildDrugVisual, INACTIVE_DRUG_VISUAL } from "../components/explorer/cell/drugVisual";

function drug(over: Partial<ActiveDrug> = {}): ActiveDrug {
  return {
    id: "x", name: "X", color: "#ffffff", viz: "cytoplasm", dose: 1, strength: 1,
    targets: [], mechanism: "", confidence: "high", channels: {}, ...over,
  };
}

function frame(drugs: ActiveDrug[], over: Partial<FrameData> = {}): FrameData {
  return {
    mass: 1, alive: true, status: "GROWING", metabolism_status: "optimal",
    divisions: 0, generation: 0, lineage: "0", env_glucose: 20, pool_glucose: 2,
    membrane_integrity: 1,
    phenotype: { transport: 1, membrane: 1, replication: 1, metabolism: 1 },
    replication: { progress: 0.3, replicating: true, complete: false },
    expression: { mrna: 40, protein: 300 },
    drugs,
    ...over,
  } as FrameData;
}

describe("DrugVisualController — untreated / recovery", () => {
  it("is inactive with no drugs (motion normal, all effects zero)", () => {
    const v = buildDrugVisual(frame([]));
    expect(v).toEqual(INACTIVE_DRUG_VISUAL);
    expect(v.motion).toBe(1);
  });

  it("recovers to inactive after washout (drugs list empty again)", () => {
    expect(buildDrugVisual(frame([])).active).toBe(false);
    expect(buildDrugVisual(null).active).toBe(false);
  });
});

describe("DrugVisualController — per-drug visual states", () => {
  it("membrane disruptor → damage, leakage, repair", () => {
    const v = buildDrugVisual(
      frame([drug({ channels: { membrane_lysis: 0.35, membrane: 0.7 } })],
        { membrane_integrity: 0.6, phenotype: { membrane: 1.4 } as Record<string, number> }),
    );
    expect(v.membraneDamage).toBeGreaterThan(0);
    expect(v.leakage).toBe(v.membraneDamage);
    expect(v.membraneRepair).toBeGreaterThan(0); // phenotype.membrane > 1
  });

  it("ATP inhibitor → ATP dims, motion slows, ribosomes stall", () => {
    const v = buildDrugVisual(
      frame([drug({ channels: { metabolism: 0.18 } })], { phenotype: { metabolism: 0.3 } as Record<string, number> }),
    );
    expect(v.atpDim).toBeGreaterThan(0);
    expect(v.motion).toBeLessThan(1);
    expect(v.ribosomeStall).toBeGreaterThan(0);
  });

  it("DNA inhibitor → fork freezes, DNA glow down, polymerase fades", () => {
    const v = buildDrugVisual(frame([drug({ channels: { replication: 0.1, mutation: 0.5 } })]));
    expect(v.forkFreeze).toBeGreaterThan(0);
    expect(v.dnaGlowDown).toBeGreaterThan(0);
    expect(v.polymeraseFade).toBe(v.forkFreeze);
    expect(v.ros).toBe(0); // mutation < 1 is not a mutagen
  });

  it("transport inhibitor → transporter block + starvation passthrough", () => {
    const v = buildDrugVisual(
      frame([drug({ channels: { transport: 0.12 } })], {
        phenotype: { transport: 0.3 } as Record<string, number>,
        signalling: { mode: "SURVIVAL", survival: true, signals: { starvation: 0.8, growth: 0.1, membrane_stress: 0.1 } },
      }),
    );
    expect(v.transportBlock).toBeGreaterThan(0);
    expect(v.starvation).toBeCloseTo(0.8);
  });

  it("oxidative stress → ROS, mutation sparks, membrane damage", () => {
    const v = buildDrugVisual(
      frame([drug({ channels: { membrane_lysis: 0.15, metabolism: 0.7, mutation: 1.8 } })],
        { membrane_integrity: 0.7, phenotype: { metabolism: 0.7 } as Record<string, number> }),
    );
    expect(v.ros).toBeGreaterThan(0);
    expect(v.mutationSparks).toBe(v.ros);
    expect(v.membraneDamage).toBeGreaterThan(0);
    expect(v.atpDim).toBeGreaterThan(0);
  });

  it("ribosome inhibitor → ribosome stall + dimmer DNA (transcription-limited)", () => {
    const v = buildDrugVisual(frame([drug({ channels: { expression: 0.2 } })]));
    expect(v.ribosomeStall).toBeGreaterThan(0);
    expect(v.dnaGlowDown).toBeGreaterThan(0);
  });
});

describe("DrugVisualController — progressive with strength & variable", () => {
  it("stronger dose (strength) yields a stronger effect", () => {
    const weak = buildDrugVisual(
      frame([drug({ strength: 0.3, channels: { membrane_lysis: 0.35 } })], { membrane_integrity: 0.8 }),
    );
    const strong = buildDrugVisual(
      frame([drug({ strength: 1.0, channels: { membrane_lysis: 0.35 } })], { membrane_integrity: 0.8 }),
    );
    expect(strong.membraneDamage).toBeGreaterThan(weak.membraneDamage);
  });

  it("deeper biological deviation yields a stronger effect (progressive onset)", () => {
    const early = buildDrugVisual(
      frame([drug({ channels: { transport: 0.12 } })], { phenotype: { transport: 0.9 } as Record<string, number> }),
    );
    const late = buildDrugVisual(
      frame([drug({ channels: { transport: 0.12 } })], { phenotype: { transport: 0.2 } as Record<string, number> }),
    );
    expect(late.transportBlock).toBeGreaterThan(early.transportBlock);
  });
});
