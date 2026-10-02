/**
 * Why a canvas request failed, in the person's words. The reason is read from the status code
 * alone: an error's own text comes from the server and may quote what was sent.
 */

import { ApiError } from "../api/client";
import { vi } from "../i18n/vi";

export function canvasReason(error: unknown): string {
  const reasons = vi.canvas.reasons;
  if (!(error instanceof ApiError)) return reasons.offline;
  if (error.status === 404) return reasons.gone;
  if (error.status === 413) return reasons.tooLarge;
  if (error.status === 507) return reasons.full;
  if (error.status >= 500) return reasons.server;
  return reasons.invalid;
}
