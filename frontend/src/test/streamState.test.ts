import { describe, expect, it } from "vitest";
import type { FrameData, StreamMessage } from "../api/types";
import { initialStreamState, latestFrame, reduceStream } from "../stream/streamState";

function frameData(mass: number): FrameData {
  return {
    mass,
    alive: true,
    status: "GROWING",
    metabolism_status: "optimal",
    divisions: 0,
    generation: 0,
    lineage: "0",
    env_glucose: 50,
    pool_glucose: 1,
    membrane_integrity: 1,
  };
}

describe("reduceStream", () => {
  it("accumulates frames in order", () => {
    let s = initialStreamState();
    const msgs: StreamMessage[] = [
      { kind: "frame", step: 0, time: 0, data: frameData(0.001) },
      { kind: "frame", step: 1, time: 0.1, data: frameData(0.002) },
    ];
    for (const m of msgs) s = reduceStream(s, m);
    expect(s.frames).toHaveLength(2);
    expect(latestFrame(s)?.data.mass).toBe(0.002);
  });

  it("collects events separately from frames", () => {
    let s = initialStreamState();
    s = reduceStream(s, { kind: "frame", step: 0, time: 0, data: frameData(0.001) });
    s = reduceStream(s, { kind: "event", step: 5, time: 0.5, type: "division", data: { division_index: 1 } });
    expect(s.frames).toHaveLength(1);
    expect(s.events).toHaveLength(1);
    expect(s.events[0].type).toBe("division");
  });

  it("records terminal status", () => {
    let s = initialStreamState();
    s = reduceStream(s, { kind: "status", status: "DONE", done: true });
    expect(s.status).toBe("DONE");
    expect(s.done).toBe(true);
  });

  it("returns null latest frame when empty", () => {
    expect(latestFrame(initialStreamState())).toBeNull();
  });
});
