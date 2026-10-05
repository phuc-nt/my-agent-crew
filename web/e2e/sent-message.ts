import type { Request } from "@playwright/test";

/**
 * What a message was sent with, apart from the name of its send. Every send carries one, of
 * its own and well formed, so a test that compares the rest still checks that it was there.
 */
export function sentMessage(request: Request): Record<string, unknown> {
  const { request_id: name, ...rest } = request.postDataJSON() as Record<string, unknown>;
  if (typeof name !== "string" || !/^[0-9a-f]{32}$/.test(name)) throw new Error(`a message went with no name of its own: ${JSON.stringify(name)}`);
  return rest;
}
