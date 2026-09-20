import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../i18n/vi";
import { addedLines } from "../lib/line-diff";
import { coachAgent, fakeAgent, FakeBackend } from "../test/fake-backend";
import { MemoryPanel } from "./memory-panel";

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  backend.agents = [fakeAgent, coachAgent];
  vitest.stubGlobal("fetch", backend.fetch);
});

const name = (id: string) => (id === "coach" ? "HLV" : "Agent");

function mount(pending = 0) {
  return render(
    <MemoryPanel
      agents={backend.agents}
      agentId="default"
      pendingProposals={pending}
      agentName={name}
    />,
  );
}

const open = (label: string) => userEvent.click(screen.getByRole("tab", { name: new RegExp(label) }));

describe("MemoryPanel", () => {
  it("saves USER.md and shows the facts the crew already knows", async () => {
    backend.userMd = "Phúc, làm sản phẩm.";
    backend.facts = [
      {
        name: "ngu-som",
        description: "Ngủ trước 23h",
        type: "preference",
        written_by: "coach",
        source: "chat",
        updated: "2026-09-20T08:00:00",
        body: "Ngủ sớm mỗi ngày.",
      },
    ];
    mount();

    const textarea = await screen.findByRole("textbox", { name: new RegExp(vi.memory.userMd) });
    expect(textarea).toHaveValue("Phúc, làm sản phẩm.");
    expect(screen.getByText("Ngủ trước 23h")).toBeInTheDocument();
    expect(screen.getByText(vi.memory.factTypes.preference)).toBeInTheDocument();

    await userEvent.type(textarea, " Thích ngắn gọn.");
    await userEvent.click(screen.getByRole("button", { name: vi.memory.save }));
    await waitFor(() => expect(backend.userMd).toContain("Thích ngắn gọn."));
  });

  it("creates a fact through the form and forgets it after a confirm", async () => {
    mount();
    await screen.findByText(vi.memory.factsEmpty);

    await userEvent.click(screen.getByRole("button", { name: vi.memory.newFact }));
    await userEvent.type(screen.getByRole("textbox", { name: vi.memory.factName }), "ca-phe");
    await userEvent.type(
      screen.getByRole("textbox", { name: vi.memory.factDescription }),
      "Thích cà phê",
    );
    await userEvent.selectOptions(screen.getByRole("combobox"), "preference");
    const form = screen.getByRole("textbox", { name: vi.memory.factName }).closest("form")!;
    await userEvent.click(within(form).getByRole("button", { name: vi.memory.save }));

    await waitFor(() => expect(backend.facts.map((f) => f.name)).toEqual(["ca-phe"]));
    expect(await screen.findByText("Thích cà phê")).toBeInTheDocument();

    vitest.spyOn(window, "confirm").mockReturnValue(true);
    await userEvent.click(screen.getByRole("button", { name: vi.memory.remove }));
    await waitFor(() => expect(backend.facts).toEqual([]));
  });

  it("edits one agent's MEMORY.md and opens a dated note", async () => {
    backend.setAgentMemory("default", {
      memory_md: "- Sếp thích trà.",
      notes: [{ day: "2026-09-19", chars: 4 }],
      note_count: 1,
    });
    backend.notes.set("default/2026-09-19", "Đã chạy bản tin.");
    mount();

    await open(vi.memory.agents);
    const memory = await screen.findByRole("textbox", { name: new RegExp(vi.memory.agentMemory) });
    expect(memory).toHaveValue("- Sếp thích trà.");

    await userEvent.click(screen.getByRole("button", { name: "2026-09-19" }));
    const note = await screen.findByRole("textbox", { name: /2026-09-19/ });
    expect(note).toHaveValue("Đã chạy bản tin.");

    await userEvent.type(note, " Xong.");
    await userEvent.click(screen.getAllByRole("button", { name: vi.memory.save })[1]);
    await waitFor(() => expect(backend.notes.get("default/2026-09-19")).toContain("Xong."));
  });

  it("switching agent asks the server for that agent's memory", async () => {
    backend.setAgentMemory("coach", { memory_md: "- HLV nhớ riêng." });
    mount();

    await open(vi.memory.agents);
    await screen.findByRole("textbox", { name: new RegExp(vi.memory.agentMemory) });
    await userEvent.selectOptions(screen.getByRole("combobox"), "coach");

    await waitFor(() =>
      expect(screen.getByRole("textbox", { name: new RegExp(vi.memory.agentMemory) })).toHaveValue(
        "- HLV nhớ riêng.",
      ),
    );
  });

  it("labels a search hit by the scope it came from", async () => {
    backend.hits = [
      { scope: "user", agent_id: "", file: "user/ca-phe.md", text: "Thích cà phê" },
      { scope: "agent", agent_id: "coach", file: "MEMORY.md", text: "- cà phê sữa" },
    ];
    mount();

    await open(vi.memory.search);
    await userEvent.type(screen.getByRole("textbox", { name: new RegExp(vi.memory.search) }), "cà phê");
    await userEvent.click(screen.getByRole("button", { name: vi.memory.search }));

    expect(await screen.findByText("Thích cà phê")).toBeInTheDocument();
    expect(screen.getByText(vi.memory.scopeUser)).toBeInTheDocument();
    expect(screen.getByText("HLV")).toBeInTheDocument();
  });

  it("approving a proposal writes the fact and moves it into the history", async () => {
    const proposal = backend.addProposal({ agent_id: "coach" });
    mount(1);

    await open(vi.memory.proposals);
    expect(await screen.findByText("Ngủ trước 23h")).toBeInTheDocument();
    expect(screen.getByText(vi.memory.proposalKinds.user_fact)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: vi.memory.approve }));
    await waitFor(() => expect(backend.proposals[0].status).toBe("approved"));
    expect(await screen.findByText(vi.memory.proposalsEmpty)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: new RegExp(vi.memory.history) }));
    expect(screen.getByText(vi.memory.proposalStatus.approved)).toBeInTheDocument();
    expect(proposal.resolved_at).not.toBeNull();
  });

  it("asks the server to consolidate and says where to watch it", async () => {
    backend.setAgentMemory("default", { memory_md: "- Sếp thích trà." });
    mount();

    await open(vi.memory.agents);
    await userEvent.click(await screen.findByRole("button", { name: vi.memory.consolidate }));

    await waitFor(() => expect(backend.consolidated).toEqual(["default"]));
    expect(await screen.findByText(vi.memory.consolidateStarted)).toBeInTheDocument();
  });

  it("says so when a consolidation is already running", async () => {
    backend.setAgentMemory("default", { memory_md: "- Sếp thích trà." });
    backend.consolidateBusy = true;
    mount();

    await open(vi.memory.agents);
    await userEvent.click(await screen.findByRole("button", { name: vi.memory.consolidate }));
    expect(await screen.findByText(vi.memory.consolidateBusy)).toBeInTheDocument();
  });

  it("shows a rewrite against what it replaces and can put that back", async () => {
    backend.setAgentMemory("default", { memory_md: "- Sếp thích trà.\n- Sếp ngủ sớm." });
    backend.addProposal({
      kind: "agent_memory_rewrite",
      name: "MEMORY.md",
      description: "Cô đọng bộ nhớ",
      body: "- Sếp thích trà.\n- Sếp ngủ sớm.",
      previous_body: "- Sếp thích trà.",
      status: "approved",
      resolved_at: "2026-09-20T09:00:00",
    });
    mount();

    await open(vi.memory.proposals);
    // The one proposal is already decided, so it only shows once the history is open.
    await userEvent.click(await screen.findByRole("button", { name: `${vi.memory.history} (1)` }));
    expect(
      await screen.findByText(vi.memory.proposalKinds.agent_memory_rewrite),
    ).toBeInTheDocument();

    vitest.spyOn(window, "confirm").mockReturnValue(true);
    await userEvent.click(screen.getByRole("button", { name: vi.memory.undo }));
    await waitFor(() =>
      expect(backend.readAgentMemory("default").memory_md).toBe("- Sếp thích trà."),
    );
  });

  it("shows an agent_memory proposal as the lines it would add", async () => {
    backend.setAgentMemory("default", { memory_md: "- Sếp thích trà." });
    backend.addProposal({
      kind: "agent_memory",
      name: "",
      description: "Ghi nhớ vòng 1",
      body: "- Sếp thích trà.\n- Đã xong vòng 1.",
    });
    mount(1);

    await open(vi.memory.proposals);
    const diff = await screen.findByText("+ - Đã xong vòng 1.");
    expect(diff).toHaveClass("added");
    expect(screen.getByText("- Sếp thích trà.")).not.toHaveClass("added");
  });
});

describe("addedLines", () => {
  it("marks only lines the current file does not already have", () => {
    expect(addedLines("a\n\nb", "a\nc")).toEqual([
      { text: "a", added: false },
      { text: "c", added: true },
    ]);
  });
});
