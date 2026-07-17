// Pure parser for the server-sent-events stream the AI endpoints emit. Each event is
// a `data: {json}` line; JSON payloads carry {delta} / {done} / {error}. Kept pure so
// the streaming reducer can be unit-tested without a network.

export interface SSEEvent {
  delta?: string;
  done?: boolean;
  error?: string;
}

/**
 * Parse whatever complete SSE frames are in `buffer`; return the parsed events and
 * the trailing partial frame (to prepend to the next chunk).
 */
export function parseSSE(buffer: string): { events: SSEEvent[]; rest: string } {
  const frames = buffer.split("\n\n");
  const rest = frames.pop() ?? "";
  const events: SSEEvent[] = [];
  for (const frame of frames) {
    const line = frame.split("\n").find((l) => l.startsWith("data: "));
    if (!line) continue;
    try {
      events.push(JSON.parse(line.slice("data: ".length)) as SSEEvent);
    } catch {
      /* ignore malformed frame */
    }
  }
  return { events, rest };
}
