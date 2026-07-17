import { describe, expect, it } from "vitest";
import type { Frame, FrameData, PetriSummary, PopulationSummary, SimEvent } from "../api/types";
import { cellRadius, cloneCounts, colonyPosition, lineageColor, lineageHue } from "../components/explorer/colony";
import { buildInspect, presentObjects, transportActivity } from "../components/explorer/inspect";
import { cloneColorRGB, gridToWorld, heatmapTexture, representativeCellFrame, viridis } from "../components/explorer/petri";
import {
  clampIndex,
  eventMarkers,
  frameIndexForStep,
  nextEventIndex,
  prevEventIndex,
} from "../components/explorer/playback";

function frame(overrides: Partial<FrameData> = {}): FrameData {
  return {
    mass: 1.5,
    alive: true,
    status: "GROWING",
    metabolism_status: "optimal",
    divisions: 1,
    generation: 1,
    lineage: "0",
    env_glucose: 30,
    pool_glucose: 1.2,
    membrane_integrity: 0.9,
    replication: { progress: 0.4, replicating: true, complete: false },
    phenotype: { transport: 1.0, membrane: 1.0, replication: 1.0, metabolism: 1.0 },
    ...overrides,
  };
}

function mkFrames(steps: number[]): Frame[] {
  return steps.map((s) => ({ step: s, time: s * 0.1, data: frame() }));
}

describe("inspect", () => {
  it("returns null when there is no frame", () => {
    expect(buildInspect("membrane", null)).toBeNull();
  });

  it("describes the membrane with integrity", () => {
    const info = buildInspect("membrane", frame({ membrane_integrity: 0.5 }))!;
    expect(info.title).toBe("Membrane");
    expect(info.values.some((v) => v.label === "integrity" && v.value === "50%")).toBe(true);
    expect(info.explanation).toMatch(/bilayer/i);
  });

  it("reports replication progress on the nucleoid", () => {
    const info = buildInspect("nucleoid", frame({ replication: { progress: 0.4, replicating: true, complete: false } }))!;
    expect(info.values.some((v) => v.label === "replication" && v.value === "40%")).toBe(true);
    expect(info.values.some((v) => v.value === "replicating")).toBe(true);
  });

  it("reflects transport phenotype in transporter activity", () => {
    const up = frame({ phenotype: { transport: 1.8, membrane: 1, replication: 1, metabolism: 1 } });
    expect(transportActivity(up)).toBe(1.8);
    const info = buildInspect("transport", up)!;
    expect(info.values.some((v) => v.label === "activity" && v.value.startsWith("1.8"))).toBe(true);
  });

  it("describes signalling survival mode when active", () => {
    const info = buildInspect(
      "signalling",
      frame({ signalling: { mode: "SURVIVAL", survival: true, signals: { starvation: 0.8, growth: 0.1, membrane_stress: 0.2 } } }),
    )!;
    expect(info.subtitle).toMatch(/survival/i);
    expect(info.values.some((v) => v.label === "mode" && v.value === "SURVIVAL")).toBe(true);
  });

  it("returns null for a signalling inspect on a non-signalling frame", () => {
    expect(buildInspect("signalling", frame())).toBeNull();
  });

  it("describes a compartment energy pool and its stress", () => {
    const f = frame({
      compartments: {
        cytosol: { energy: 20, stressed: false },
        nucleoid: { energy: 0.1, stressed: true },
        membrane_zone: { energy: 5, stressed: false },
      },
    });
    const info = buildInspect("energy.nucleoid", f)!;
    expect(info.values.some((v) => v.value.includes("stressed"))).toBe(true);
  });

  it("lists present objects for the scenario", () => {
    const base = presentObjects(frame());
    expect(base).toEqual(["membrane", "cytosol", "nucleoid", "transport"]);

    const rich = presentObjects(
      frame({
        field_glc: [1, 2, 3],
        signalling: { mode: "NORMAL", survival: false, signals: { starvation: 0, growth: 1, membrane_stress: 0 } },
        compartments: { cytosol: { energy: 10, stressed: false } },
      }),
    );
    expect(rich).toContain("nutrients");
    expect(rich).toContain("signalling");
    expect(rich).toContain("energy.cytosol");
  });
});

function popFrame(overrides: Partial<PopulationSummary> = {}): FrameData {
  const population: PopulationSummary = {
    step: 10,
    size: 3,
    alive: 3,
    dead: 1,
    total_ever: 4,
    born: 3,
    died: 1,
    generations: 2,
    medium_glucose: 40,
    dominant_lineage: "0",
    dominant_fraction: 0.66,
    lineages: 2,
    mean_genotype: { transport: 1.1, membrane: 1, replication: 1, metabolism: 1 },
    total_biomass: 2.4,
    cells: [
      { id: 0, lineage: "0.0", root: "0", generation: 1, mass: 0.8, alive: true },
      { id: 1, lineage: "0.1", root: "0", generation: 1, mass: 0.6, alive: true },
      { id: 2, lineage: "1", root: "1", generation: 0, mass: 0.5, alive: true },
      { id: 3, lineage: "0.0.1", root: "0", generation: 2, mass: 0.1, alive: false },
    ],
    ...overrides,
  };
  return { ...(popFrameBase() as FrameData), population };
}
function popFrameBase(): Partial<FrameData> {
  return { mass: 0, alive: true, status: null, metabolism_status: null, divisions: 0, generation: 0, lineage: null, env_glucose: 0, pool_glucose: 0, membrane_integrity: 1 };
}

describe("colony", () => {
  it("lays out cells deterministically and sizes them by mass", () => {
    expect(colonyPosition(0)).toEqual([0, 0]);
    expect(colonyPosition(5)).toEqual(colonyPosition(5)); // stable
    expect(cellRadius(1)).toBeGreaterThan(cellRadius(0));
    expect(cellRadius(1e9)).toBeLessThanOrEqual(0.42); // clamped
  });

  it("assigns a stable hue per clone and dims dead cells", () => {
    expect(lineageHue("0")).toBe(lineageHue("0"));
    expect(lineageColor("0", true)).not.toBe(lineageColor("0", false));
  });

  it("counts living cells per clone, largest first", () => {
    const counts = cloneCounts(popFrame().population!.cells);
    expect(counts[0]).toEqual({ root: "0", count: 2 }); // clone 0 has 2 living, clone 1 has 1
    expect(counts.map((c) => c.root)).toEqual(["0", "1"]);
  });
});

describe("population inspect", () => {
  it("presents only the colony object for a population frame", () => {
    expect(presentObjects(popFrame())).toEqual(["population"]);
  });

  it("summarises the colony", () => {
    const info = buildInspect("population", popFrame())!;
    expect(info.title).toBe("Colony");
    expect(info.values.some((v) => v.label === "living cells" && v.value === "3")).toBe(true);
    expect(info.values.some((v) => v.label === "births / deaths" && v.value === "3 / 1")).toBe(true);
  });

  it("inspects an individual cell by id", () => {
    const info = buildInspect("cell.2", popFrame())!;
    expect(info.title).toBe("Cell #2");
    expect(info.values.some((v) => v.label === "clone (root)" && v.value === "#1")).toBe(true);
  });

  it("returns null for a missing cell id", () => {
    expect(buildInspect("cell.99", popFrame())).toBeNull();
  });
});

function petriFrame(overrides: Partial<PetriSummary> = {}): FrameData {
  const petri: PetriSummary = {
    step: 20,
    alive: 5,
    dead: 3,
    born: 7,
    died: 3,
    colonies: 2,
    n_clones: 3,
    dominant_clone: 1,
    dominant_fraction: 0.6,
    generations: 3,
    occupancy: 0.42,
    total_nutrient: 120,
    mean_genotype: { transport: 1.2, yield: 0.9 },
    grid: [4, 4],
    hm_size: [2, 2],
    heatmaps: { population: [0, 1, 2, 0], nutrient: [0.5, 1, 0, 0.2], mutation: [0, 2, 1, 0], atp: [0.1, 0.3, 0, 0] },
    clone_map: [-1, 0, 1, -1],
    cells: {
      x: [0, 1, 2, 3, 1],
      y: [0, 1, 2, 3, 2],
      clone: [0, 1, 1, 2, 1],
      energy: [1.8, 0.5, 2.2, 0.0, 1.0],
      mut: [0, 1, 3, 2, 0],
      count: 5,
      cap: 4000,
    },
    ...overrides,
  };
  return { ...(popFrameBase() as FrameData), petri };
}

describe("petri colormaps & mapping", () => {
  it("gives distinct clone colours and a dark colour for empty (-1)", () => {
    expect(cloneColorRGB(0)).not.toEqual(cloneColorRGB(1));
    expect(cloneColorRGB(-1)).toEqual([24, 30, 46]);
  });

  it("viridis moves from dark blue to yellow", () => {
    const lo = viridis(0);
    const hi = viridis(1);
    expect(lo[2]).toBeGreaterThan(lo[0]); // dark blue: more blue than red
    expect(hi[0]).toBeGreaterThan(hi[2]); // yellow: more red than blue
  });

  it("maps grid coordinates into the dish plane (centre at origin, y flipped)", () => {
    const [cx, cy] = gridToWorld(0, 0, 5, 5);
    expect(cx).toBeLessThan(0); // left edge
    expect(cy).toBeGreaterThan(0); // row 0 at the top (+Y)
  });

  it("builds an RGBA heat-map buffer of the right size", () => {
    const { data, rows, cols } = heatmapTexture(petriFrame().petri!, "population");
    expect(rows).toBe(2);
    expect(cols).toBe(2);
    expect(data.length).toBe(2 * 2 * 4);
  });

  it("colours the clone heat map by dominant clone and marks empty cells transparent", () => {
    const { data } = heatmapTexture(petriFrame().petri!, "clone");
    expect(data[3]).toBe(40); // first coarse cell (-1) → low alpha
    expect(data[1 * 4 + 3]).toBe(235); // occupied cell → opaque
  });
});

describe("petri inspect & enter-cell", () => {
  it("presents only the dish object for a petri frame", () => {
    expect(presentObjects(petriFrame())).toEqual(["petri"]);
  });

  it("summarises the dish", () => {
    const info = buildInspect("petri", petriFrame())!;
    expect(info.title).toBe("Petri dish");
    expect(info.values.some((v) => v.label === "occupancy" && v.value === "42%")).toBe(true);
  });

  it("inspects an individual dish cell", () => {
    const info = buildInspect("petricell.2", petriFrame())!;
    expect(info.title).toContain("(2, 2)");
    expect(info.values.some((v) => v.label === "mutations" && v.value === "3")).toBe(true);
  });

  it("builds a representative single-cell frame to enter", () => {
    const summary = petriFrame().petri!;
    const rep = representativeCellFrame(summary.cells, 0, summary)!;
    expect(rep.status).toBe("GROWING"); // energy 1.8 > 1.5
    expect(rep.genotype!.transport).toBe(1.2); // from colony mean genotype
    expect(representativeCellFrame(summary.cells, 99, summary)).toBeNull();
  });
});

describe("playback", () => {
  it("clamps indices to the frame range", () => {
    expect(clampIndex(-5, 10)).toBe(0);
    expect(clampIndex(99, 10)).toBe(9);
    expect(clampIndex(3, 0)).toBe(0);
  });

  it("maps a step to the last frame at or before it", () => {
    const frames = mkFrames([0, 5, 10, 15]);
    expect(frameIndexForStep(frames, 12)).toBe(2); // step 10
    expect(frameIndexForStep(frames, 5)).toBe(1);
    expect(frameIndexForStep(frames, -1)).toBe(0);
  });

  it("places event markers on the timeline", () => {
    const frames = mkFrames([0, 5, 10, 15]);
    const events: SimEvent[] = [
      { step: 5, time: 0.5, type: "mutation", data: {} },
      { step: 15, time: 1.5, type: "division", data: {} },
    ];
    const markers = eventMarkers(events, frames);
    expect(markers).toHaveLength(2);
    expect(markers[0]).toMatchObject({ type: "mutation", index: 1 });
    expect(markers[1]).toMatchObject({ type: "division", index: 3, position: 1 });
  });

  it("finds next and previous event indices", () => {
    const frames = mkFrames([0, 5, 10, 15]);
    const events: SimEvent[] = [
      { step: 5, time: 0.5, type: "mutation", data: {} },
      { step: 15, time: 1.5, type: "division", data: {} },
    ];
    const markers = eventMarkers(events, frames);
    expect(nextEventIndex(markers, 0)).toBe(1);
    expect(nextEventIndex(markers, 1)).toBe(3);
    expect(nextEventIndex(markers, 3)).toBeNull();
    expect(prevEventIndex(markers, 3)).toBe(1);
    expect(prevEventIndex(markers, 1)).toBeNull();
  });
});
