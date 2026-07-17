// The study's knowledge graph as an SVG DAG: parameters (left) → outcome metrics,
// with signed, weighted edges from the discovered relationships. Grows automatically
// as more experiments accumulate. Data-driven — no hand-authored biology.

import { useMemo } from "react";
import type { KnowledgeGraphData } from "../../api/types";
import { edgeColor, layoutGraph } from "./graph";

const W = 640;
const H = 300;
const PAD = 60;

export function KnowledgeGraph({ data }: { data: KnowledgeGraphData }) {
  const layout = useMemo(() => layoutGraph(data), [data]);

  if (data.nodes.length === 0) {
    return <p className="muted">No relationships discovered yet — run more experiments to grow the graph.</p>;
  }

  const px = (x: number) => PAD + x * (W - 2 * PAD);
  const py = (y: number) => PAD * 0.6 + y * (H - 1.2 * PAD);

  return (
    <svg className="kg-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Knowledge graph">
      <defs>
        <marker id="kg-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
          <path d="M0,0 L8,4 L0,8 Z" fill="#5b6b8a" />
        </marker>
      </defs>
      {layout.edges.map((e, i) => {
        const x1 = px(e.x1);
        const y1 = py(e.y1);
        const x2 = px(e.x2);
        const y2 = py(e.y2);
        return (
          <line
            key={i}
            x1={x1}
            y1={y1}
            x2={x2}
            y2={y2}
            stroke={edgeColor(e.sign)}
            strokeWidth={1 + e.strength * 3}
            strokeOpacity={0.5 + e.strength * 0.4}
            markerEnd="url(#kg-arrow)"
          />
        );
      })}
      {layout.nodes.map((n) => {
        const x = px(n.x);
        const y = py(n.y);
        const isParam = n.kind === "parameter";
        return (
          <g key={n.id} transform={`translate(${x},${y})`}>
            <rect
              x={-56}
              y={-14}
              width={112}
              height={28}
              rx={isParam ? 6 : 14}
              fill={isParam ? "#1a2740" : "#12233a"}
              stroke={isParam ? "#60a5fa" : "#4ade80"}
              strokeWidth={1.2}
            />
            <text x={0} y={4} textAnchor="middle" fontSize={11} fill="#e6edf7">
              {n.label.length > 16 ? n.label.slice(0, 15) + "…" : n.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
