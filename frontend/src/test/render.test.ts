import { describe, expect, it } from "vitest";
import type { FrameData } from "../api/types";
import { buildCellVisual } from "../components/explorer/cell/biomap";
import {
  channelGeometry,
  enzymeVariants,
  proteinVariants,
} from "../components/explorer/cell/shapes";

function frame(over: Partial<FrameData> = {}): FrameData {
  return {
    mass: 1.0, alive: true, status: "growing", metabolism_status: null,
    divisions: 0, generation: 0, lineage: null, env_glucose: 20, pool_glucose: 2,
    membrane_integrity: 1, expression: { mrna: 50, protein: 300 }, ...over,
  } as FrameData;
}

describe("biomap: crowding + enzyme density (data-driven)", () => {
  it("enzymes track metabolic activity + substrate, zero when dead", () => {
    expect(buildCellVisual(frame(), 0.6).enzymeCount).toBeGreaterThan(0);
    expect(buildCellVisual(frame({ alive: false }), 0).enzymeCount).toBe(0);
  });

  it("crowding is dense and rises with biomass", () => {
    const big = buildCellVisual(frame({ mass: 3.0 }), 0.6).crowdingCount;
    const small = buildCellVisual(frame({ mass: 0.2 }), 0.6).crowdingCount;
    expect(big).toBeGreaterThan(small);
    expect(big).toBeGreaterThan(100); // hundreds of instances → a crowded cytoplasm
  });
});

describe("procedural molecular geometry", () => {
  it("provides multiple distinct protein variants (no identical copies)", () => {
    const variants = proteinVariants();
    expect(variants.length).toBeGreaterThanOrEqual(4);
    // Distinct geometries have differing vertex counts / bounds.
    const counts = new Set(variants.map((g) => g.getAttribute("position").count));
    expect(counts.size).toBeGreaterThan(1);
  });

  it("builds enzyme variants and a channel pore (not a bare cylinder)", () => {
    expect(enzymeVariants().length).toBeGreaterThanOrEqual(2);
    const ch = channelGeometry();
    expect(ch.getAttribute("position").count).toBeGreaterThan(24); // a multi-subunit barrel
  });

  it("caches geometry (stable across calls, no per-frame rebuild flicker)", () => {
    expect(proteinVariants()).toBe(proteinVariants());
    expect(channelGeometry()).toBe(channelGeometry());
  });
});
