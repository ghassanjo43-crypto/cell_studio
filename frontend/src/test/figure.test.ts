import { describe, expect, it } from "vitest";
import { legendFor, niceStep, scaleBar } from "../components/explorer/figure";

describe("figure export helpers", () => {
  it("rounds magnitudes to nice 1/2/5 steps", () => {
    expect(niceStep(1.2)).toBe(1);
    expect(niceStep(2.6)).toBe(2);
    expect(niceStep(6)).toBe(5);
    expect(niceStep(8)).toBe(10);
    expect(niceStep(23)).toBe(20);
    expect(niceStep(0)).toBe(0);
  });

  it("computes a scale bar near the target pixel length with a nice unit count", () => {
    const bar = scaleBar(10, 130); // 10 px per site, want ~130px
    expect(bar.units).toBe(10); // niceStep(13) = 10 sites
    expect(bar.px).toBe(100); // 10 * 10
    expect(scaleBar(0, 130)).toEqual({ units: 0, px: 0 }); // guards against zero
  });

  it("builds a clone legend, or a metric note", () => {
    const clones = legendFor("clone", ["rgb(1,2,3)", "rgb(4,5,6)"]);
    expect(clones).toEqual([
      { color: "rgb(1,2,3)", label: "clone #0" },
      { color: "rgb(4,5,6)", label: "clone #1" },
    ]);
    const nutrient = legendFor("nutrient", []);
    expect(nutrient[0].label).toMatch(/nutrient/);
  });
});
