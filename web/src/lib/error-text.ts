import { ApiError } from "../api/client";
import { vi } from "../i18n/vi";

/** A validation dump: FastAPI's 422 carries a JSON list of what failed, not a sentence. */
const dump = (detail: string) => /^[[{]/.test(detail);
/** The framework's stock 404s, which name no thing: "Not Found", "agent not found". */
const stockNotFound = (detail: string) => /^[\w ]*not found$/i.test(detail);

/**
 * The sentence to show for a request that failed.
 *
 * What the server wrote as a sentence is kept: its refusals say what to change. What a
 * person could not act on is put in words instead — a network that never reached the
 * server (fetch throws a bare TypeError), a crash on the server, a validation dump or a
 * stock "not found". `notFound` names what a 404 lost, where the caller knows it.
 */
export function errorText(error: unknown, notFound?: string): string {
  if (error instanceof ApiError) {
    const detail = error.message.trim();
    if (error.status >= 500) return vi.requestErrors.server(error.status);
    if (error.status === 404 && (stockNotFound(detail) || !detail)) return notFound ?? vi.requestErrors.notFound;
    if (dump(detail)) return vi.requestErrors.invalid;
    return detail || vi.requestErrors.status(error.status);
  }
  if (error instanceof TypeError) return vi.requestErrors.network;
  if (error instanceof Error) return error.message;
  return String(error);
}

/** `errorText` for a request that sends a message or resumes a turn, where a 409 means the
 *  conversation waits on a decision. */
export function turnErrorText(error: unknown): string {
  if (error instanceof ApiError && error.status === 409) return vi.busyConflict;
  return errorText(error);
}
