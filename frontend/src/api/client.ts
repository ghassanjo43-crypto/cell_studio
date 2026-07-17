// Base HTTP client: token storage, JSON helpers, and typed errors.
//
// In development, requests go to the Vite proxy at "/api" (forwarded to the
// backend). Override with VITE_API_URL for production builds.

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "/api";
const TOKEN_KEY = "vcs_token";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function parseError(res: Response): Promise<never> {
  let detail = res.statusText;
  try {
    const body = await res.json();
    if (body && typeof body.detail === "string") detail = body.detail;
    else if (Array.isArray(body?.detail)) detail = body.detail.map((d: { msg: string }) => d.msg).join("; ");
  } catch {
    /* non-JSON error body */
  }
  throw new ApiError(res.status, detail);
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { headers: { ...authHeaders() } });
  if (!res.ok) return parseError(res);
  return res.json() as Promise<T>;
}

export async function apiSend<T>(path: string, method: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) return parseError(res);
  return res.json() as Promise<T>;
}

// --- Drug Interaction Studio -------------------------------------------------
/** The drug library (representative mechanisms). */
export async function listDrugs(): Promise<import("./types").Drug[]> {
  return apiGet<import("./types").Drug[]>("/drugs");
}

/** Inject / update / remove a drug on a running simulation in real time. */
export async function injectDrug(
  simId: number,
  command: { action: "add" | "update" | "remove"; drug_id: string; dose?: number; duration?: number | null },
): Promise<unknown> {
  return apiSend(`/simulations/${simId}/drugs`, "POST", command);
}

/** Grounded interpretation of a drug's effect from an untreated vs treated frame. */
export async function interpretDrug(body: {
  drugs: string[];
  untreated: import("./types").FrameData;
  treated: import("./types").FrameData;
  narrate?: boolean;
}): Promise<import("./types").DrugInterpretResult> {
  return apiSend<import("./types").DrugInterpretResult>("/pharmacology/interpret", "POST", body);
}

// POST and consume a server-sent-events stream, invoking `onDelta` with the
// accumulated text so far. Resolves with the full text when the stream completes.
export async function streamSSE(
  path: string,
  body: unknown,
  onDelta: (text: string) => void,
): Promise<string> {
  const { parseSSE } = await import("./sse");
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body ?? {}),
  });
  if (!res.ok || !res.body) return parseError(res);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let full = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const { events, rest } = parseSSE(buffer);
    buffer = rest;
    for (const ev of events) {
      if (ev.error) throw new ApiError(500, ev.error);
      if (ev.delta) {
        full += ev.delta;
        onDelta(full);
      }
      if (ev.done) return full;
    }
  }
  return full;
}

// Fetch a file (CSV/JSON export) with auth and trigger a browser download.
export async function downloadFile(path: string, filename: string): Promise<void> {
  const res = await fetch(`${API_BASE}${path}`, { headers: { ...authHeaders() } });
  if (!res.ok) return parseError(res);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// OAuth2 password grant expects form-encoded data.
export async function apiLoginForm(path: string, username: string, password: string): Promise<{ access_token: string }> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ username, password }),
  });
  if (!res.ok) return parseError(res);
  return res.json() as Promise<{ access_token: string }>;
}

// Build the WebSocket URL for a simulation stream (same host, ws scheme).
export function streamUrl(simId: number, token: string): string {
  const explicit = import.meta.env.VITE_WS_URL as string | undefined;
  const base =
    explicit ??
    (API_BASE.startsWith("http")
      ? API_BASE.replace(/^http/, "ws")
      : `${location.origin.replace(/^http/, "ws")}`);
  return `${base}/ws/simulations/${simId}?token=${encodeURIComponent(token)}`;
}
