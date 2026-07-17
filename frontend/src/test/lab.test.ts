import { describe, expect, it } from "vitest";
import { paramsForScenario, parseSweepValues, SWEEP_PARAMS } from "../components/lab/sweepParams";

describe("sweep params", () => {
  it("filters parameters by base scenario", () => {
    const petri = paramsForScenario("petri").map((p) => p.field);
    expect(petri).toContain("nutrient_pattern");
    expect(petri).toContain("max_steps"); // "*" applies everywhere
    expect(petri).not.toContain("glucose_mmol"); // single-cell only

    const lifecycle = paramsForScenario("lifecycle").map((p) => p.field);
    expect(lifecycle).toContain("glucose_mmol");
    expect(lifecycle).not.toContain("nutrient_pattern");
  });

  it("every param lists at least one scenario and an example", () => {
    for (const p of SWEEP_PARAMS) {
      expect(p.scenarios.length).toBeGreaterThan(0);
      expect(p.example.length).toBeGreaterThan(0);
    }
  });

  it("parses numeric sweep values, dropping blanks and NaN", () => {
    expect(parseSweepValues("10, 30, 60", "number")).toEqual([10, 30, 60]);
    expect(parseSweepValues(" 1 , , 2 ,x", "number")).toEqual([1, 2]);
  });

  it("parses categorical sweep values as strings", () => {
    expect(parseSweepValues("uniform, gradient , patches", "category")).toEqual([
      "uniform", "gradient", "patches",
    ]);
  });
});
