// Chronological lifecycle event timeline (growth, replication, mutation, division,
// death), newest first.

import type { SimEvent } from "../api/types";
import { eventStyle } from "./theme";

interface EventTimelineProps {
  events: SimEvent[];
}

function summarize(event: SimEvent): string {
  const d = event.data;
  switch (event.type) {
    case "division":
      return `→ lineage ${(d.daughter_lineages as string[] | undefined)?.join(", ") ?? ""}`;
    case "mutation":
      return `${d.target as string}: ${formatNum(d.old)} → ${formatNum(d.new)}`;
    case "death":
      return `cause: ${d.cause as string}`;
    case "gene_activated":
      return `${d.gene as string}`;
    case "drug_injected":
      return `${d.name as string} @ ${formatNum(d.dose)}×`;
    case "drug_dose_changed":
      return `${d.name as string} → ${formatNum(d.dose)}×`;
    case "drug_removed":
      return `${d.name as string} removed`;
    default:
      return "";
  }
}

function formatNum(v: unknown): string {
  return typeof v === "number" ? v.toFixed(3) : String(v);
}

export function EventTimeline({ events }: EventTimelineProps) {
  const ordered = [...events].reverse();
  return (
    <div className="timeline">
      <div className="timeline-title">Lifecycle events ({events.length})</div>
      {ordered.length === 0 ? (
        <div className="timeline-empty">No events yet.</div>
      ) : (
        <ul className="timeline-list">
          {ordered.map((e, i) => {
            const style = eventStyle(e.type);
            return (
              <li key={`${e.step}-${e.type}-${i}`} className="timeline-item">
                <span className="timeline-icon" style={{ color: style.color }}>
                  {style.icon}
                </span>
                <span className="timeline-step">t={e.time.toFixed(1)}h</span>
                <span className="timeline-label" style={{ color: style.color }}>
                  {style.label}
                </span>
                <span className="timeline-detail">{summarize(e)}</span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
