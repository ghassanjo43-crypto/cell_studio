import { describe, expect, it } from "vitest";
import type { Frame, FrameData, SimEvent } from "../api/types";
import { buildNarrationLog, narrationUpTo } from "../components/explorer/presentation/narration";
import { eventShot, tourScenes } from "../components/explorer/presentation/tour";

function fd(overrides: Partial<FrameData> = {}): FrameData {
  return {
    mass: 1, alive: true, status: "GROWING", metabolism_status: "optimal",
    divisions: 0, generation: 0, lineage: "0", env_glucose: 20, pool_glucose: 1,
    membrane_integrity: 1, replication: { progress: 0, replicating: false, complete: false },
    phenotype: { transport: 1, membrane: 1, replication: 1, metabolism: 1 }, ...overrides,
  };
}
const frame = (step: number, data: FrameData): Frame => ({ step, time: step * 0.1, data });

describe("narration", () => {
  it("narrates replication start and progress milestones from state", () => {
    const frames: Frame[] = [
      frame(0, fd({ replication: { progress: 0, replicating: false, complete: false } })),
      frame(1, fd({ replication: { progress: 0.1, replicating: true, complete: false } })),
      frame(2, fd({ replication: { progress: 0.5, replicating: true, complete: false } })),
    ];
    const log = buildNarrationLog(frames, [], "teaching");
    const texts = log.map((l) => l.text);
    expect(texts.some((t) => /replication has started/i.test(t))).toBe(true);
    expect(texts.some((t) => /50% complete/.test(t))).toBe(true);
  });

  it("turns events into narration, phrased by mode", () => {
    const frames: Frame[] = [frame(0, fd()), frame(10, fd())];
    const events: SimEvent[] = [{ step: 10, time: 1, type: "division", data: {} }];
    const teaching = buildNarrationLog(frames, events, "teaching").find((l) => l.kind === "division");
    const investor = buildNarrationLog(frames, events, "investor").find((l) => l.kind === "division");
    expect(teaching!.text).toMatch(/cytokinesis|daughter/i);
    expect(investor!.text).toMatch(/synthetic|autonomously/i); // investor voice differs
    expect(investor!.text).not.toBe(teaching!.text);
  });

  it("only shows narration up to the current step", () => {
    const frames: Frame[] = [frame(0, fd()), frame(20, fd())];
    const events: SimEvent[] = [
      { step: 5, time: 0.5, type: "mutation", data: {} },
      { step: 15, time: 1.5, type: "death", data: { cause: "starvation" } },
    ];
    const log = buildNarrationLog(frames, events, "teaching");
    expect(narrationUpTo(log, 10).length).toBe(1); // only the mutation so far
    expect(narrationUpTo(log, 20).length).toBe(2);
  });

  it("never emits colony_founded spam", () => {
    const log = buildNarrationLog([frame(0, fd())], [{ step: 0, time: 0, type: "colony_founded", data: {} }], "teaching");
    expect(log.length).toBe(0);
  });
});

describe("tour", () => {
  it("scripts single-cell scenes, dish scenes, colony scenes", () => {
    const single = tourScenes(fd()).map((s) => s.key);
    expect(single[0]).toBe("overview");
    expect(single.some((k) => k === "genome")).toBe(true);

    const dish = tourScenes(fd({ petri: { step: 0, alive: 3, dead: 0, born: 3, died: 0, colonies: 2, n_clones: 2, dominant_clone: 0, dominant_fraction: 1, generations: 0, occupancy: 0.1, total_nutrient: 10, mean_genotype: {}, grid: [4, 4], hm_size: [2, 2], heatmaps: { population: [], nutrient: [], mutation: [], atp: [] }, clone_map: [], cells: { x: [], y: [], clone: [], energy: [], mut: [], count: 0, cap: 0 } } }));
    expect(dish.some((s) => s.key === "nutrients")).toBe(true);
  });

  it("captions are data-driven", () => {
    const scenes = tourScenes(fd({ replication: { progress: 0.65, replicating: true, complete: false } }));
    const genome = scenes.find((s) => s.key === "genome")!;
    expect(genome.caption(fd({ replication: { progress: 0.65, replicating: true, complete: false } }))).toMatch(/65% complete/);
  });

  it("maps important events to camera shots", () => {
    expect(eventShot("division", fd())!.id).toBe("nucleoid");
    expect(eventShot("survival_mode_entered", fd())!.id).toBe("signalling");
    expect(eventShot("nope", fd())).toBeNull();
  });
});
