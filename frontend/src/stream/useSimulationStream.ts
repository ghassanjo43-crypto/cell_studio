// React hook wrapping a simulation WebSocket stream.

import { useEffect, useReducer, useState } from "react";
import { streamUrl } from "../api/client";
import type { StreamMessage } from "../api/types";
import { initialStreamState, reduceStream, type StreamState } from "./streamState";

export interface StreamHook extends StreamState {
  connected: boolean;
}

// Mount this hook's owner with a `key` tied to simId so accumulated state resets
// when the target simulation changes.
export function useSimulationStream(
  simId: number | null,
  token: string | null,
  enabled: boolean,
): StreamHook {
  const [state, dispatch] = useReducer(reduceStream, undefined, initialStreamState);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!enabled || simId == null || !token) return;
    const ws = new WebSocket(streamUrl(simId, token));
    ws.onopen = () => setConnected(true);
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data) as StreamMessage;
        dispatch(msg);
      } catch {
        /* ignore malformed frames */
      }
    };
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);
    return () => ws.close();
    // Re-open when the target simulation changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [simId, token, enabled]);

  return { ...state, connected };
}
