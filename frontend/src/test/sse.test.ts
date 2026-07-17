import { describe, expect, it } from "vitest";
import { parseSSE } from "../api/sse";

describe("parseSSE", () => {
  it("parses complete delta frames and keeps the trailing partial", () => {
    const { events, rest } = parseSSE('data: {"delta":"Hello "}\n\ndata: {"delta":"world"}\n\ndata: {"del');
    expect(events).toEqual([{ delta: "Hello " }, { delta: "world" }]);
    expect(rest).toBe('data: {"del');
  });

  it("recognises the done event", () => {
    const { events } = parseSSE('data: {"delta":"x"}\n\ndata: {"done":true}\n\n');
    expect(events[1]).toEqual({ done: true });
  });

  it("surfaces error events", () => {
    const { events } = parseSSE('data: {"error":"boom"}\n\n');
    expect(events[0].error).toBe("boom");
  });

  it("ignores malformed frames without throwing", () => {
    const { events } = parseSSE("data: not-json\n\ndata: {\"delta\":\"ok\"}\n\n");
    expect(events).toEqual([{ delta: "ok" }]);
  });

  it("reconstructs a streamed answer by concatenating deltas", () => {
    const chunks = ['data: {"delta":"the cell "}\n\n', 'data: {"delta":"divided"}\n\ndata: {"done":true}\n\n'];
    let buffer = "";
    let full = "";
    for (const c of chunks) {
      buffer += c;
      const { events, rest } = parseSSE(buffer);
      buffer = rest;
      for (const e of events) if (e.delta) full += e.delta;
    }
    expect(full).toBe("the cell divided");
  });
});
