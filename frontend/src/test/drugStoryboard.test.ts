import { describe, expect, it } from "vitest";
import type { ActiveDrug, FrameData } from "../api/types";
import { buildStoryboard, classifyDrug } from "../components/pharmacology/storyboard";

function drug(over: Partial<ActiveDrug> = {}): ActiveDrug {
  return {
    id: "x", name: "X", color: "#fff", viz: "cytoplasm", dose: 1, strength: 1,
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

const WALL = drug({ id: "cell-wall-synthesis-inhibitor", name: "Cell-wall Inhibitor", viz: "membrane", channels: { membrane: 0.12 } });
const DNA = drug({ id: "dna-replication-inhibitor", name: "DNA Inhibitor", viz: "dna", channels: { replication: 0.1, mutation: 0.5 } });
const ATP = drug({ id: "atp-synthesis-inhibitor", name: "ATP Inhibitor", channels: { metabolism: 0.18 } });
const TRANSPORT = drug({ id: "nutrient-transport-inhibitor", name: "Transport Inhibitor", viz: "transport", channels: { transport: 0.12 } });
const OX = drug({ id: "oxidative-stress-inducer", name: "Oxidative Stress", channels: { membrane_lysis: 0.15, metabolism: 0.7, mutation: 1.8 } });

describe("drug classification", () => {
  it("maps channels to the right cascade class", () => {
    expect(classifyDrug({ membrane_lysis: 0.35, membrane: 0.7 })).toBe("disruptor");
    expect(classifyDrug({ membrane: 0.12 })).toBe("wall");
    expect(classifyDrug({ replication: 0.1, mutation: 0.5 })).toBe("dna");
    expect(classifyDrug({ metabolism: 0.18 })).toBe("atp");
    expect(classifyDrug({ transport: 0.12 })).toBe("transport");
    expect(classifyDrug({ expression: 0.2 })).toBe("expression");
    expect(classifyDrug({ mutation: 1.8 })).toBe("oxidative");
    expect(classifyDrug({})).toBe("generic");
  });
});

describe("storyboard — presence + per-drug cascades", () => {
  it("is null with no drugs", () => {
    expect(buildStoryboard(frame([]))).toBeNull();
    expect(buildStoryboard(null)).toBeNull();
  });

  it("cell-wall inhibitor: target → synthesis → … → lysis", () => {
    const s = buildStoryboard(frame([WALL]))!;
    expect(s.primaryTarget).toMatch(/wall/i);
    expect(s.stages.map((x) => x.label)).toEqual(
      ["Wall synthesis slows", "Repair vesicles increase", "Membrane weakens", "Rupture zones appear", "Lysis"],
    );
    expect(s.fate).toMatch(/Lysis/);
    expect(s.currentLabel).toBe("Wall synthesis slows");
    expect(s.nextLabel).toBe("Repair vesicles increase");
  });

  it("DNA inhibitor: fork stalls → polymerases disappear → glow fades → no division", () => {
    const s = buildStoryboard(frame([DNA]))!;
    expect(s.stages[0].label).toMatch(/fork stalls/i);
    expect(s.stages.map((x) => x.label)).toContain("No division");
    expect(s.fate).toMatch(/Division/);
    expect(s.eta).toMatch(/division|non-lethal/i);
  });

  it("ATP inhibitor: ATP dims → transport slows → ribosomes stop → crisis", () => {
    const s = buildStoryboard(frame([ATP], { phenotype: { metabolism: 0.3 } as Record<string, number> }))!;
    expect(s.primaryTarget).toMatch(/metabolism|ATP/i);
    expect(s.stages[0].label).toMatch(/ATP output dims/i);
    expect(s.stages.map((x) => x.label)).toContain("Ribosomes stop");
  });

  it("transport inhibitor: glucose accumulates → transporters inactive → starvation", () => {
    const s = buildStoryboard(frame([TRANSPORT], { phenotype: { transport: 0.3 } as Record<string, number> }))!;
    expect(s.stages[0].label).toMatch(/Glucose accumulates outside/i);
    expect(s.stages.map((x) => x.label)).toContain("Starvation signalling increases");
  });

  it("oxidative stress: ROS → sparks → oxidation → DNA damage → death", () => {
    const s = buildStoryboard(frame([OX], { membrane_integrity: 0.7, phenotype: { metabolism: 0.7 } as Record<string, number> }))!;
    expect(s.stages[0].label).toMatch(/ROS appears/i);
    expect(s.stages.map((x) => x.label)).toContain("Mutation sparks");
    expect(s.fate).toMatch(/oxidative/i);
  });
});

describe("storyboard — progression + ETA (data-driven)", () => {
  it("advances the current stage as the biology deteriorates", () => {
    const early = buildStoryboard(frame([WALL], { membrane_integrity: 1.0 }))!;
    const late = buildStoryboard(frame([WALL], { membrane_integrity: 0.2 }))!;
    expect(late.currentIndex).toBeGreaterThan(early.currentIndex);
  });

  it("estimates time to death from a declining integrity trend", () => {
    const hist = Array.from({ length: 10 }, (_, i) => frame([WALL], { membrane_integrity: 0.9 - i * 0.05 }));
    const s = buildStoryboard(hist[hist.length - 1], hist)!;
    expect(s.eta).toMatch(/steps to lysis/i);
  });

  it("reports recovery when the trend is rising, and death when the cell is dead", () => {
    const rising = Array.from({ length: 10 }, (_, i) => frame([WALL], { membrane_integrity: 0.4 + i * 0.05 }));
    expect(buildStoryboard(rising[rising.length - 1], rising)!.eta).toMatch(/recover/i);
    expect(buildStoryboard(frame([WALL], { alive: false }))!.eta).toMatch(/died/i);
  });

  it("marks stage status (done / active / pending) along the cascade", () => {
    const s = buildStoryboard(frame([WALL], { membrane_integrity: 0.2 }))!;
    expect(s.stages[0].status).toBe("done");
    expect(s.stages[s.currentIndex].status).toMatch(/active|done/);
    const pending = s.stages.slice(s.currentIndex + 1);
    if (pending.length) expect(pending[pending.length - 1].status).toBe("pending");
  });
});
