// The Drug Effect Storyboard UI: a "Drug Response" summary (primary target, current +
// next response, ETA) over an animated cascade timeline. Purely presentational — every
// value comes from buildStoryboard(), which reads only measured simulation variables.

import { useMemo } from "react";
import type { FrameData } from "../../api/types";
import { buildStoryboard } from "./storyboard";

const STATUS_COLOR: Record<string, string> = {
  done: "#4ade80",
  active: "#fbbf24",
  pending: "#475569",
};

export function DrugStoryboard({
  frame, history,
}: {
  frame?: FrameData | null;
  history?: FrameData[];
}) {
  const story = useMemo(() => buildStoryboard(frame, history ?? []), [frame, history]);

  if (!story) {
    return (
      <div className="story-empty">
        Apply or inject a drug to see its response storyboard — the affected pathway will
        light up stage by stage, driven by the live simulation variables.
      </div>
    );
  }

  return (
    <div className="storyboard">
      <div className="story-head">
        <span className="drug-dot" style={{ background: story.color }} />
        <span className="story-drug">{story.drugName}</span>
        {story.otherActive > 0 && <span className="story-more">+{story.otherActive} more</span>}
      </div>

      {/* Drug Response summary. */}
      <div className="story-summary">
        <div><span>Primary target</span><b>{story.primaryTarget}</b></div>
        <div><span>Current response</span><b style={{ color: "#fbbf24" }}>{story.currentLabel}</b></div>
        <div><span>Next predicted</span><b>{story.nextLabel ?? "—"}</b></div>
        <div><span>Predicted fate</span><b>{story.fate}</b></div>
        <div><span>Est. recovery/death</span><b>{story.eta}</b></div>
      </div>

      {/* Animated cascade timeline. */}
      <ol className="story-timeline">
        {story.stages.map((s, i) => (
          <li key={s.key} className={`story-stage is-${s.status} ${i === story.currentIndex ? "is-current" : ""}`}>
            <span className="story-node" style={{ background: STATUS_COLOR[s.status] }} />
            <div className="story-stage-body">
              <div className="story-stage-label">{s.label}</div>
              <div className="story-bar">
                <div
                  className="story-bar-fill"
                  style={{ width: `${Math.round(s.progress * 100)}%`, background: story.color }}
                />
              </div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
