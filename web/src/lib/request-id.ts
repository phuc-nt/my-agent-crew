/**
 * A name for one send. The server takes a send of a given name once: made again under the
 * same name, by a tab that never heard the first answer, it starts nothing new and is
 * answered with what became of the first. Random, so two tabs never pick the same one;
 * `getRandomValues` and not `randomUUID`, which a page served over plain http on the home
 * network does not have.
 */
export function newRequestId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}
