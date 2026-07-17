import { afterEach, describe, expect, it, vi } from "vitest";
import { aiApi } from "../api/endpoints";
import { setToken } from "../api/client";

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

function stubJson(body: unknown): ReturnType<typeof vi.fn> {
  const spy = vi.fn((_input: RequestInfo | URL, _init?: RequestInit) =>
    Promise.resolve(new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    })),
  );
  vi.stubGlobal("fetch", spy);
  return spy;
}

describe("aiApi", () => {
  it("posts a design prompt and returns the validated proposal", async () => {
    setToken("t");
    const spy = stubJson({ config: { scenario: "evolution" }, rationale: "because" });
    const result = await aiApi.design("an evolving cell");
    expect(result.config.scenario).toBe("evolution");
    expect(result.rationale).toBe("because");
    const [url, init] = spy.mock.calls[0];
    expect(String(url)).toContain("/ai/design");
    expect((init as RequestInit).method).toBe("POST");
  });

  it("posts an interpret question for a simulation", async () => {
    const spy = stubJson({ answer: "it starved", grounding: "divisions=2" });
    const result = await aiApi.interpret(7, "why die?");
    expect(result.answer).toBe("it starved");
    expect(String(spy.mock.calls[0][0])).toContain("/ai/simulations/7/interpret");
  });
});
