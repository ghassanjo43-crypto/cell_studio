// Pure helpers for the AI Scientist page: knowledge-graph layout, confidence styling,
// and the example research goals. Kept free of React/DOM so they can be unit-tested.

import type { Confidence, GraphEdge, GraphNode, KnowledgeGraphData } from "../../api/types";

// Mechanistic left→right ordering of outcome metrics (supply → biomass → survival →
// division → population). Used only for layout, not to assert facts.
export const METRIC_ORDER = [
  "nutrient_depletion",
  "biomass_peak",
  "survival_time",
  "divisions",
  "peak_population",
];

export interface PositionedNode extends GraphNode {
  x: number;
  y: number;
  col: number;
}

export interface PositionedEdge extends GraphEdge {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface GraphLayout {
  nodes: PositionedNode[];
  edges: PositionedEdge[];
}

/** Column index for a node: parameters on the left, metrics grouped by mechanism. */
export function columnFor(node: GraphNode): number {
  if (node.kind === "parameter") return 0;
  const i = METRIC_ORDER.indexOf(node.id);
  if (i < 0) return 1;
  return 1 + Math.floor(i / 2); // pairs of metrics share a column
}

/**
 * Lay the graph out in normalized [0,1] coordinates: nodes are placed in columns
 * (params → metrics) and stacked evenly within each column; edges carry endpoint
 * coordinates so an SVG can draw them directly.
 */
export function layoutGraph(data: KnowledgeGraphData): GraphLayout {
  const cols = new Map<number, GraphNode[]>();
  for (const n of data.nodes) {
    const c = columnFor(n);
    (cols.get(c) ?? cols.set(c, []).get(c)!).push(n);
  }
  const maxCol = Math.max(1, ...[...cols.keys()]);
  const pos = new Map<string, PositionedNode>();
  for (const [col, nodes] of cols) {
    nodes.forEach((n, i) => {
      const x = maxCol === 0 ? 0.5 : col / maxCol;
      const y = nodes.length === 1 ? 0.5 : i / (nodes.length - 1);
      pos.set(n.id, { ...n, x, y, col });
    });
  }
  const nodes = [...pos.values()];
  const edges: PositionedEdge[] = [];
  for (const e of data.edges) {
    const a = pos.get(e.source);
    const b = pos.get(e.target);
    if (!a || !b) continue;
    edges.push({ ...e, x1: a.x, y1: a.y, x2: b.x, y2: b.y });
  }
  return { nodes, edges };
}

const CONF: Record<Confidence, { label: string; color: string }> = {
  high: { label: "High", color: "#4ade80" },
  medium: { label: "Medium", color: "#fbbf24" },
  low: { label: "Low", color: "#93a1b8" },
};

export function confidenceMeta(level: Confidence): { label: string; color: string } {
  return CONF[level] ?? CONF.low;
}

/** Colour for an edge by its sign (positive/negative/none). */
export function edgeColor(sign: GraphEdge["sign"]): string {
  if (sign === "+") return "#4ade80";
  if (sign === "-") return "#fb7185";
  return "#60a5fa";
}

export interface GoalPreset {
  label: string;
  goal: string;
}

// The example research goals from the product spec, surfaced as one-click presets.
export const GOAL_PRESETS: GoalPreset[] = [
  { label: "Survive longer", goal: "I want the cell to survive longer." },
  { label: "Maximum biomass", goal: "I want maximum biomass." },
  { label: "Rapid division", goal: "I want rapid division." },
  { label: "Starvation resistance", goal: "I want starvation resistance." },
  { label: "Minimum ATP consumption", goal: "I want minimum ATP consumption." },
  { label: "Higher protein production", goal: "I want higher protein production." },
];
