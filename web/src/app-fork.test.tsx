import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { App } from "./app";
import { vi } from "./i18n/vi";
import { FakeBackend, FakeEventSource, storedMessage } from "./test/fake-backend";

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  FakeEventSource.instances = [];
  vitest.stubGlobal("fetch", backend.fetch);
  vitest.stubGlobal("EventSource", FakeEventSource);
  window.location.hash = "";
});

afterEach(() => vitest.unstubAllGlobals());

/** Two finished turns, each bubble carrying the numeric id a reload reports. */
function twoTurns(title: string) {
  return backend.create({
    title,
    messages: [
      storedMessage("user", "câu đầu gõ sai", { id: "1", seq: 1 }),
      storedMessage("assistant", "trả lời câu đầu", { id: "2", seq: 2 }),
      storedMessage("user", "câu sau", { id: "3", seq: 3 }),
      storedMessage("assistant", "trả lời câu sau", { id: "4", seq: 4 }),
    ],
  });
}

const sidebar = () => within(screen.getByRole("navigation", { name: vi.conversations }));

async function open(title: string) {
  await userEvent.click(await sidebar().findByRole("button", { name: new RegExp(title) }));
  await screen.findByRole("heading", { level: 1, name: title });
}

function forkAt(bubble: number) {
  const target = screen.getAllByTestId("message-user")[bubble];
  return userEvent.click(within(target).getByRole("button", { name: vi.fork.fromHere }));
}

describe("editing and resending from a saved message", () => {
  it("opens the branch with the old words ready to edit, and links back to an untouched source", async () => {
    const source = twoTurns("Việc");
    render(<App />);
    await open("Việc");
    expect(screen.getAllByTestId("message-user")).toHaveLength(2);
    expect(screen.queryByTestId("fork-origin")).toBeNull();

    await forkAt(1);

    await screen.findByRole("heading", { level: 1, name: "Việc (nhánh)" });
    const box = screen.getByRole("textbox", { name: /Nhắn cho/ });
    await waitFor(() => expect(box).toHaveValue("câu sau"));
    await waitFor(() => expect(box).toHaveFocus());
    await waitFor(() => expect(screen.getAllByTestId("message-user")).toHaveLength(1));
    expect(screen.getByTestId("message-user")).toHaveTextContent("câu đầu gõ sai");
    expect(screen.getByTestId("message-assistant")).toHaveTextContent("trả lời câu đầu");
    expect(sidebar().getByRole("button", { name: /Việc \(nhánh\)/ })).toHaveAttribute("aria-current", "page");
    const origin = screen.getByTestId("fork-origin");
    expect(origin).toHaveTextContent(vi.fork.from);
    expect(origin).toHaveTextContent("Việc");

    await userEvent.click(within(origin).getByRole("button", { name: "Việc" }));

    await screen.findByRole("heading", { level: 1, name: "Việc" });
    await waitFor(() => expect(screen.getAllByTestId("message-user")).toHaveLength(2));
    expect(screen.queryByTestId("fork-origin")).toBeNull();
    expect(backend.conversations.get(source.id)?.messages).toHaveLength(4);
  });

  it("reports a refused fork on its own conversation only", async () => {
    twoTurns("Việc");
    backend.create({ title: "Khác", messages: [storedMessage("user", "chào", { id: "9", seq: 1 })] });
    vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) =>
      String(input).endsWith("/fork")
        ? new Response(JSON.stringify({ detail: "lỗi" }), { status: 500, headers: { "content-type": "application/json" } })
        : backend.fetch(input, init),
    );
    render(<App />);
    await open("Việc");

    await forkAt(0);

    expect(await screen.findByTestId("fork-error")).toHaveTextContent(vi.fork.failed);
    await open("Khác");
    expect(screen.queryByTestId("fork-error")).toBeNull();
    await open("Việc");
    expect(screen.queryByTestId("fork-error")).toBeNull();
  });
});
