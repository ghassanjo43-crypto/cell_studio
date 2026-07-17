// Pure builder for the always-on scientific legend: the colour/where key for whatever
// scene is showing. Every entry corresponds to a real rendered element.

import type { FrameData, HeatmapMetric } from "../../api/types";
import { statusColor } from "../theme";
import { cloneColorRGB } from "./petri";

export interface LegendItem {
  color: string;
  label: string;
}

const rgb = (c: [number, number, number]) => `rgb(${c[0]},${c[1]},${c[2]})`;

export function legendItems(frame: FrameData | null, metric: HeatmapMetric): LegendItem[] {
  if (!frame) return [];

  if (frame.petri) {
    const p = frame.petri;
    const clones: LegendItem[] = Array.from({ length: Math.min(p.n_clones, 8) }, (_, i) => ({
      color: rgb(cloneColorRGB(i)),
      label: `clone #${i}`,
    }));
    return [
      ...clones,
      { color: "#e2e8f0", label: "brightness = ATP energy" },
      { color: "#fde047", label: `floor = ${metric}` },
    ];
  }

  if (frame.population) {
    return [
      { color: "#4ade80", label: "cell = clone colour" },
      { color: "#38bdf8", label: "size = biomass" },
      { color: "#fbbf24", label: "medium disc = glucose" },
    ];
  }

  // Single cell.
  const items: LegendItem[] = [
    { color: statusColor(frame.status), label: "membrane (status)" },
    { color: "#22d3ee", label: "transporters" },
    { color: "#60a5fa", label: "channels" },
    { color: "#a78bfa", label: "genome" },
    { color: "#67e8f9", label: "ATP" },
    { color: "#fbbf24", label: "glucose" },
    { color: "#a3e635", label: "metabolites" },
    { color: "#e2e8f0", label: "ribosomes" },
  ];
  if (frame.signalling) {
    items.push({ color: "#f472b6", label: "signalling / receptors" });
  }
  if (frame.compartments) {
    items.push({ color: "#38bdf8", label: "compartments (energy)" });
  }
  return items;
}
