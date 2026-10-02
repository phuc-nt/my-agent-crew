import { fireEvent, screen, within } from "@testing-library/react";
import { vi } from "../i18n/vi";
import { landed } from "./canvas-hook";
import type { FakeBackend } from "./fake-backend";

/** The history of the panel `openPanel` opened, in the text's place. */
export const history = () => screen.getByRole("region", { name: vi.canvas.historyTitle });
export const historyShown = () => screen.queryByRole("region", { name: vi.canvas.historyTitle }) !== null;

export const rows = () => within(history()).getAllByRole("listitem").map((row) => row.textContent);
export const picked = () => within(history()).getByRole("button", { current: true }).textContent;
export const diff = () => history().querySelector(".canvas-diff")?.textContent ?? null;
export const restoreButton = () => within(history()).getByRole("button", { name: vi.canvas.restore });

export async function openHistory() {
  fireEvent.click(screen.getByRole("button", { name: vi.canvas.history }));
  await landed();
}

export async function pick(version: number) {
  fireEvent.click(within(history()).getByRole("button", { name: new RegExp(`^v${version} `) }));
  await landed();
}

/** The saves and restores sent, in order. */
export const writes = (backend: FakeBackend) =>
  backend.requests
    .filter((request) => request.method === "PUT" || request.method === "POST")
    .map(({ method, path, body }) => ({ method, path, body }));

/** v1 by the person, v2 by Ming, and v4 by the person with v3 folded away. */
export function threeVersions(backend: FakeBackend) {
  backend.canvas.add({ title: "Ghi chú", content: "một" });
  backend.canvas.write("a1", "một\nhai", { author: "agent:ming" });
  backend.canvas.write("a1", "một\nhai\nbốn", { author: "user", gap: 1 });
}
