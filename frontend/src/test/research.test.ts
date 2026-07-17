import { describe, expect, it } from "vitest";
import type { KnowledgeGraphData } from "../api/types";
import {
  columnFor,
  confidenceMeta,
  edgeColor,
  GOAL_PRESETS,
  layoutGraph,
  METRIC_ORDER,
} from "../components/research/graph";

describe("knowledge-graph layout", () => {
  it("puts parameters in column 0 and metrics further right", () => {
    expect(columnFor({ id: "glucose_mmol", label: "Glucose", kind: "parameter" })).toBe(0);
    expect(columnFor({ id: "nutrient_depletion", label: "N", kind: "metric" })).toBeGreaterThan(0);
    // Later metrics in the mechanistic order sit in later columns.
    const early = columnFor({ id: METRIC_ORDER[0], label: "", kind: "metric" });
    const late = columnFor({ id: METRIC_ORDER[METRIC_ORDER.length - 1], label: "", kind: "metric" });
    expect(late).toBeGreaterThanOrEqual(early);
  });

  it("positions nodes in [0,1] and resolves edge endpoints", () => {
    const data: KnowledgeGraphData = {
      nodes: [
        { id: "glucose_mmol", label: "Glucose", kind: "parameter" },
        { id: "biomass_peak", label: "Peak biomass", kind: "metric" },
        { id: "survival_time", label: "Survival", kind: "metric" },
      ],
      edges: [
        { source: "glucose_mmol", target: "biomass_peak", sign: "+", strength: 0.8, kind: "increases" },
      ],
    };
    const layout = layoutGraph(data);
    expect(layout.nodes).toHaveLength(3);
    for (const n of layout.nodes) {
      expect(n.x).toBeGreaterThanOrEqual(0);
      expect(n.x).toBeLessThanOrEqual(1);
      expect(n.y).toBeGreaterThanOrEqual(0);
      expect(n.y).toBeLessThanOrEqual(1);
    }
    expect(layout.edges).toHaveLength(1);
    const e = layout.edges[0];
    // Edge starts at the parameter (x smaller) and points to the metric (x larger).
    expect(e.x1).toBeLessThan(e.x2);
  });

  it("drops edges whose endpoints are missing", () => {
    const data: KnowledgeGraphData = {
      nodes: [{ id: "a", label: "A", kind: "parameter" }],
      edges: [{ source: "a", target: "ghost", sign: "+", strength: 1, kind: "increases" }],
    };
    expect(layoutGraph(data).edges).toHaveLength(0);
  });

  it("handles an empty graph", () => {
    expect(layoutGraph({ nodes: [], edges: [] })).toEqual({ nodes: [], edges: [] });
  });
});

describe("confidence + edge styling", () => {
  it("maps confidence levels to labels + colours", () => {
    expect(confidenceMeta("high").label).toBe("High");
    expect(confidenceMeta("medium").label).toBe("Medium");
    expect(confidenceMeta("low").label).toBe("Low");
    expect(confidenceMeta("high").color).not.toEqual(confidenceMeta("low").color);
  });

  it("colours edges by sign", () => {
    expect(edgeColor("+")).not.toEqual(edgeColor("-"));
    expect(edgeColor("0")).toBeTruthy();
  });
});

describe("goal presets", () => {
  it("covers the six product example goals", () => {
    expect(GOAL_PRESETS).toHaveLength(6);
    const text = GOAL_PRESETS.map((g) => g.goal.toLowerCase()).join(" ");
    for (const kw of ["survive", "biomass", "division", "starvation", "atp", "protein"]) {
      expect(text).toContain(kw);
    }
  });
});
