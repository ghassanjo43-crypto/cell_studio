// Start / pause / resume / stop controls, enabled per current status.

import type { SimulationStatus } from "../api/types";

interface ControlsProps {
  status: SimulationStatus;
  busy: boolean;
  onStart: () => void;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
}

export function SimulationControls({ status, busy, onStart, onPause, onResume, onStop }: ControlsProps) {
  const canStart = status === "CREATED" || status === "STOPPED";
  const canPause = status === "RUNNING" || status === "QUEUED";
  const canResume = status === "PAUSED";
  const canStop = !["DONE", "STOPPED", "FAILED"].includes(status);

  return (
    <div className="controls">
      <button className="btn btn-primary" disabled={busy || !canStart} onClick={onStart}>
        ▶ Start
      </button>
      <button className="btn" disabled={busy || !canPause} onClick={onPause}>
        ⏸ Pause
      </button>
      <button className="btn" disabled={busy || !canResume} onClick={onResume}>
        ⏵ Resume
      </button>
      <button className="btn btn-danger" disabled={busy || !canStop} onClick={onStop}>
        ⏹ Stop
      </button>
      <span className={`status-badge status-${status.toLowerCase()}`}>{status}</span>
    </div>
  );
}
