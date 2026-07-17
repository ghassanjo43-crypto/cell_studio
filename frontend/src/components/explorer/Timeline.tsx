// Timeline replay control: scrub through recorded frames and replay biological
// events (growth, signalling, mutation, replication, division, death). Event markers
// are placed along the track; play/pause and prev/next-event step the position.

import type { Frame } from "../../api/types";
import { eventStyle } from "../theme";
import type { EventMarker } from "./playback";
import { nextEventIndex, prevEventIndex } from "./playback";

interface TimelineProps {
  frames: Frame[];
  markers: EventMarker[];
  index: number;
  following: boolean;
  playing: boolean;
  onScrub: (index: number) => void;
  onTogglePlay: () => void;
  onLive: () => void;
  onRestart?: () => void;
}

export function Timeline({ frames, markers, index, following, playing, onScrub, onTogglePlay, onLive, onRestart }: TimelineProps) {
  const last = Math.max(0, frames.length - 1);
  const current = frames[Math.min(index, last)];
  const step = current?.step ?? 0;
  const time = current?.time ?? 0;

  const prev = prevEventIndex(markers, index);
  const next = nextEventIndex(markers, index);

  return (
    <div className="timeline" data-testid="timeline">
      <div className="timeline-controls">
        <button className="btn btn-small" onClick={() => onScrub(0)} title="Jump to start" disabled={frames.length === 0}>
          ⏮
        </button>
        <button
          className="btn btn-small"
          onClick={() => prev !== null && onScrub(prev)}
          title="Previous event"
          disabled={prev === null}
        >
          ⤺
        </button>
        <button className="btn btn-small" onClick={onTogglePlay} title={playing ? "Pause" : "Play"} disabled={frames.length === 0}>
          {playing ? "⏸" : "⏵"}
        </button>
        {onRestart ? (
          <button className="btn btn-small" onClick={onRestart} title="Replay from the start" disabled={frames.length === 0}>
            ⟳
          </button>
        ) : null}
        <button
          className="btn btn-small"
          onClick={() => next !== null && onScrub(next)}
          title="Next event"
          disabled={next === null}
        >
          ⤻
        </button>
        <button
          className={`btn btn-small ${following ? "btn-live" : ""}`}
          onClick={onLive}
          title="Follow the live run"
          disabled={frames.length === 0}
        >
          ● live
        </button>
      </div>

      <div className="timeline-track-wrap">
        <input
          className="timeline-slider"
          type="range"
          min={0}
          max={last}
          value={Math.min(index, last)}
          onChange={(e) => onScrub(Number(e.target.value))}
          aria-label="timeline"
        />
        <div className="timeline-markers">
          {markers.map((m, i) => {
            const s = eventStyle(m.type);
            return (
              <button
                key={i}
                className="timeline-marker"
                style={{ left: `${m.position * 100}%`, background: s.color }}
                title={`${s.label} @ step ${m.step}`}
                onClick={() => onScrub(m.index)}
              />
            );
          })}
        </div>
      </div>

      <div className="timeline-readout">
        {following ? "live" : "replay"} · step {step} · t={time.toFixed(2)} · frame {Math.min(index, last) + 1}/{frames.length || 1}
      </div>
    </div>
  );
}
