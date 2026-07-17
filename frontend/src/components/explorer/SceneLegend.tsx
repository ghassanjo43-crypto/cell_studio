// A compact, always-on scientific legend: the colour/where key for whatever the
// scene is currently showing. Every entry maps to a real rendered element.

import type { FrameData, HeatmapMetric } from "../../api/types";
import { legendItems } from "./legendItems";

export function SceneLegend({ frame, metric }: { frame: FrameData | null; metric: HeatmapMetric }) {
  const items = legendItems(frame, metric);
  if (!items.length) return null;
  return (
    <div className="scene-legend" data-testid="scene-legend">
      {items.map((it) => (
        <div key={it.label} className="legend-line">
          <span className="legend-dot" style={{ background: it.color }} />
          {it.label}
        </div>
      ))}
    </div>
  );
}
