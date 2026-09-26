import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { App } from "./app";
import { vi } from "./i18n/vi";
import { FakeBackend, FakeEventSource, coachAgent, fakeAgent } from "./test/fake-backend";

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  FakeEventSource.instances = [];
  vitest.stubGlobal("fetch", backend.fetch);
  vitest.stubGlobal("EventSource", FakeEventSource);
  window.location.hash = "";
});

afterEach(() => vitest.unstubAllGlobals());

const command = (name: string) => ({ name, description: "", path: `/k/${name}.md` });

/** The names the list offers right after a lone '/' in the box. */
async function offered(): Promise<string[]> {
  const box = screen.getByRole("textbox", { name: /Nhắn cho agent/ });
  await userEvent.clear(box);
  await userEvent.type(box, "/");
  const names = within(screen.getByRole("listbox")).getAllByRole("option").map((o) => o.textContent ?? "");
  await userEvent.clear(box);
  return names;
}

describe("the commands the composer offers", () => {
  // The server expands a command with the kit of the agent that receives the message, so
  // offering another agent's commands would send a '/name' that nobody there understands.
  it("are those of the agent the open conversation talks to", async () => {
    backend.agents = [
      { ...fakeAgent, commands: [command("tong-ket")] },
      { ...coachAgent, commands: [command("plan")] },
    ];
    const delegated = backend.create({ title: "Việc của HLV", agent_id: "coach", parent_call_id: "tc-1" });
    backend.approvals = [
      { id: "ap", conversation_id: delegated.id, message_id: "m", tool_call_id: "tc", tool_name: "write_file", arguments: {}, status: "approved", created_at: "2026-09-20T01:00:00Z", expires_at: null, resolved_at: "2026-09-20T01:01:00Z", agent_id: "coach" },
    ];
    render(<App />);

    // Nothing open yet: a message goes to the master, so its kit is the one on offer.
    await screen.findByText(vi.welcomeTitleFor("Agent"));
    expect(await offered()).toEqual(["/tong-ket"]);

    // A delegate's conversation is not in the sidebar; it opens from the approval history.
    await userEvent.click(screen.getByRole("button", { name: /Quản lý/ }));
    await userEvent.click(screen.getByRole("button", { name: new RegExp(vi.approvalsTab) }));
    const history = await screen.findByTestId("approval-history");
    await userEvent.click(within(history).getByRole("button", { name: vi.openConversation }));
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Việc của HLV");

    expect(await offered()).toEqual(["/plan"]);
  });
});
