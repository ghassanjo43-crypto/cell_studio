// Pure reducer for the simulation stream. Kept separate from the React hook so it
// can be unit-tested without a WebSocket or DOM.

import type { Frame, SimEvent, SimulationStatus, StreamMessage } from "../api/types";

export interface StreamState {
  frames: Frame[];
  events: SimEvent[];
  status: SimulationStatus | null;
  done: boolean;
}

export const MAX_FRAMES = 5000;

export function initialStreamState(): StreamState {
  return { frames: [], events: [], status: null, done: false };
}

export function reduceStream(state: StreamState, msg: StreamMessage): StreamState {
  switch (msg.kind) {
    case "frame": {
      const frame: Frame = { step: msg.step, time: msg.time, data: msg.data };
      const frames = [...state.frames, frame];
      // Cap memory: keep the most recent MAX_FRAMES.
      if (frames.length > MAX_FRAMES) frames.splice(0, frames.length - MAX_FRAMES);
      return { ...state, frames };
    }
    case "event": {
      const event: SimEvent = { step: msg.step, time: msg.time, type: msg.type, data: msg.data };
      return { ...state, events: [...state.events, event] };
    }
    case "status":
      return { ...state, status: msg.status, done: msg.done };
    default:
      return state;
  }
}

export function latestFrame(state: StreamState): Frame | null {
  return state.frames.length ? state.frames[state.frames.length - 1] : null;
}
