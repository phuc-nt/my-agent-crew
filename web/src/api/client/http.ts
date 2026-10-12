import { readSse } from "../sse";
import type { AgentEvent } from "../types";

export class ApiError extends Error {
  /** `detail` is the server's `detail` as sent, so a caller can read a structured one; the
   *  message stays a string for the callers that only show or compare it. */
  constructor(
    public readonly status: number,
    message: string,
    public readonly detail: unknown = undefined,
  ) {
    super(message);
  }
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(init.headers ?? {}) },
  });
  if (!response.ok) throw await failure(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function failure(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    const message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    return new ApiError(response.status, message, body.detail);
  } catch {
    return new ApiError(response.status, response.statusText || `HTTP ${response.status}`);
  }
}

/** Reads a turn's events off `path`. False when the server had none to send. */
export async function follow(
  path: string,
  init: RequestInit,
  onEvent: (event: AgentEvent) => void,
): Promise<boolean> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { ...init.headers, accept: "text/event-stream" },
  });
  if (!response.ok) throw await failure(response);
  if (response.status === 204) return false;
  if (!response.body) throw new ApiError(response.status, "empty stream");
  await readSse(response.body, onEvent);
  return true;
}

export async function stream(
  path: string,
  body: unknown,
  onEvent: (event: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const init = { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body), signal };
  if (!(await follow(path, init, onEvent))) throw new ApiError(204, "empty stream");
}

export function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}
