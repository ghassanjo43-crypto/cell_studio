import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiGet, apiSend, setToken, streamUrl } from "../api/client";

function mockFetch(status: number, body: unknown): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("api client", () => {
  it("returns parsed JSON on success", async () => {
    mockFetch(200, { id: 1, email: "a@b.com" });
    const user = await apiGet<{ id: number }>("/auth/me");
    expect(user.id).toBe(1);
  });

  it("throws ApiError with detail on failure", async () => {
    mockFetch(409, { detail: "Email already registered" });
    await expect(apiSend("/auth/register", "POST", {})).rejects.toMatchObject({
      status: 409,
      message: "Email already registered",
    } satisfies Partial<ApiError>);
  });

  it("attaches the bearer token when present", async () => {
    setToken("tok123");
    const spy = vi.fn((_input: RequestInfo | URL, _init?: RequestInit) =>
      Promise.resolve(new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } })),
    );
    vi.stubGlobal("fetch", spy);
    await apiGet("/projects");
    const init = spy.mock.calls[0][1];
    const headers = (init?.headers ?? {}) as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer tok123");
  });
});

describe("streamUrl", () => {
  it("builds a ws url with the token", () => {
    const url = streamUrl(7, "abc");
    expect(url).toContain("/ws/simulations/7");
    expect(url).toContain("token=abc");
    expect(url.startsWith("ws")).toBe(true);
  });
});
