import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { FactInfo, RunInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { lineDiff } from "../lib/line-diff";
import { coachAgent, fakeAgent, FakeBackend, fakeRun } from "../test/fake-backend";
import { MemoryPanel } from "./memory-panel";
import { runOutcome } from "./run-chip";
import { formatDateTime } from "./run-timeline";

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  backend.agents = [fakeAgent, coachAgent];
  vitest.stubGlobal("fetch", backend.fetch);
});

const name = (id: string) => (id === "coach" ? "HLV" : "Agent");

function panel(pending = 0, runs: RunInfo[] = []) {
  return (
    <MemoryPanel
      agents={backend.agents}
      agentId="default"
      pendingProposals={pending}
      agentName={name}
      runs={runs}
    />
  );
}

function mount(pending = 0, runs: RunInfo[] = []) {
  return render(panel(pending, runs));
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
      notes: [{ day: "2026-09-19", chars: 4, date: "2026-09-19" }],
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

  it("lists two notes of the same day as two entries", async () => {
    backend.setAgentMemory("default", {
      memory_md: "",
      notes: [
        { day: "2026-09-19-1030", chars: 9, date: "2026-09-19" },
        { day: "2026-09-19", chars: 4, date: "2026-09-19" },
      ],
      note_count: 2,
    });
    backend.notes.set("default/2026-09-19-1030", "Giữa buổi.");
    mount();

    await open(vi.memory.agents);
    await userEvent.click(await screen.findByRole("button", { name: "2026-09-19-1030" }));
    expect(await screen.findByRole("textbox", { name: /2026-09-19-1030/ })).toHaveValue(
      "Giữa buổi.",
    );
    expect(screen.getByRole("button", { name: "2026-09-19" })).toBeInTheDocument();
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

  it("follows the consolidation it started, then re-reads the memory and the proposals", async () => {
    backend.setAgentMemory("default", { memory_md: "- Sếp thích trà." });
    const { rerender } = mount();
    await open(vi.memory.agents);
    await userEvent.click(await screen.findByRole("button", { name: vi.memory.consolidate }));
    expect(await screen.findByText(vi.memory.consolidateStarted)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: vi.memory.consolidate })).toBeDisabled();

    // The run wrote a note and left a rewrite to approve; neither was on screen before.
    backend.setAgentMemory("default", {
      memory_md: "- Sếp thích trà.",
      notes: [{ day: "2026-09-26", chars: 12, date: "2026-09-26" }],
      note_count: 1,
    });
    backend.addProposal({ kind: "agent_memory_rewrite", description: "Cô đọng bộ nhớ" });
    const run = fakeRun({ id: "mem-1", source: "memory:consolidate", conversation_id: null, summary: "Đã đề xuất." });
    rerender(panel(0, [run]));

    expect(await screen.findByText(runOutcome(run))).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "2026-09-26" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: vi.memory.consolidate })).toBeEnabled();
    await open(vi.memory.proposals);
    expect(await screen.findByText("Cô đọng bộ nhớ")).toBeInTheDocument();
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

const savedFact = (overrides: Partial<FactInfo> = {}): FactInfo => ({
  name: "ngu-som",
  description: "Ngủ trước 23h",
  type: "preference",
  written_by: "coach",
  source: "chat",
  updated: "2026-09-20T08:00:00",
  body: "Ngủ sớm mỗi ngày.",
  ...overrides,
});

const decisionPosts = () =>
  backend.requests.filter((r) => r.method === "POST" && r.path.startsWith("/memory/proposals/"));

describe("MemoryPanel proposal review", () => {
  it("shows a pending rewrite as removed and added lines, in order, with a local time", async () => {
    backend.addProposal({
      kind: "agent_memory_rewrite",
      name: "MEMORY.md",
      description: "Cô đọng bộ nhớ",
      previous_body: "- Sếp thích trà.\n- Sếp dị ứng tôm.\n- Sếp ngủ sớm.",
      body: "- Sếp thích trà.\n- Sếp ngủ sớm.\n- Sếp chạy bộ.",
    });
    mount(1);

    await open(vi.memory.proposals);
    const diff = (await screen.findByText("- - Sếp dị ứng tôm.")).closest("pre")!;
    expect([...diff.children].map((row) => [row.className, row.textContent])).toEqual([
      ["", "  - Sếp thích trà."],
      ["removed", "- - Sếp dị ứng tôm."],
      ["", "  - Sếp ngủ sớm."],
      ["added", "+ - Sếp chạy bộ."],
    ]);
    expect(screen.getByText(`Agent · ${formatDateTime("2026-09-20T07:00:00")}`)).toBeInTheDocument();
    expect(screen.queryByText(/2026-09-20T07:00:00/)).toBeNull();
  });

  it("shows the exact fact a forget drops and approves it only after a confirm", async () => {
    backend.facts = [savedFact()];
    backend.addProposal({ kind: "user_forget", description: "", body: "" });
    mount(1);

    await open(vi.memory.proposals);
    const card = (await screen.findByText(vi.memory.forgetWhat)).closest("li")!;
    expect(within(card).getByText("Ngủ trước 23h")).toBeInTheDocument();
    expect(within(card).getByText("Ngủ sớm mỗi ngày.")).toBeInTheDocument();

    const confirm = vitest.spyOn(window, "confirm").mockReturnValue(false);
    await userEvent.click(within(card).getByRole("button", { name: vi.memory.approve }));
    expect(confirm).toHaveBeenCalledWith(vi.memory.confirmForget("Ngủ trước 23h"));
    expect(decisionPosts()).toHaveLength(0);

    confirm.mockReturnValue(true);
    await userEvent.click(within(card).getByRole("button", { name: vi.memory.approve }));
    await waitFor(() => expect(backend.proposals[0].status).toBe("approved"));
  });

  it("says when a forget names a fact that is no longer there", async () => {
    backend.addProposal({ kind: "user_forget", name: "da-xoa", description: "", body: "" });
    mount(1);

    await open(vi.memory.proposals);
    expect(await screen.findByText(vi.memory.forgetMissing("da-xoa"))).toBeInTheDocument();
  });

  it("warns that a fact overwrites the saved one and shows what it replaces", async () => {
    backend.facts = [savedFact({ description: "Ngủ trước 22h", body: "Ngủ trước 22h mỗi tối." })];
    backend.addProposal();
    mount(1);

    await open(vi.memory.proposals);
    expect(await screen.findByText(vi.memory.overwrite("Ngủ trước 22h"))).toBeInTheDocument();
    expect(screen.getByText("- Ngủ trước 22h mỗi tối.")).toHaveClass("removed");
    expect(screen.getByText("+ Ngủ sớm mỗi ngày.")).toHaveClass("added");
  });

  it("does not warn about an overwrite for a fact that is new", async () => {
    backend.facts = [savedFact({ name: "ca-phe", description: "Thích cà phê" })];
    backend.addProposal();
    mount(1);

    await open(vi.memory.proposals);
    expect(await screen.findByText("Ngủ sớm mỗi ngày.")).toBeInTheDocument();
    expect(screen.queryByText(vi.memory.overwrite("Thích cà phê"))).toBeNull();
  });

  it("disables both buttons while a decision is in flight and sends it once", async () => {
    backend.addProposal();
    let release!: () => void;
    const gate = new Promise<void>((resolve) => (release = resolve));
    vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init: RequestInit = {}) => {
      if (init.method === "POST" && String(input).includes("/memory/proposals/")) await gate;
      return backend.fetch(input, init);
    });
    mount(1);

    await open(vi.memory.proposals);
    const approve = await screen.findByRole("button", { name: vi.memory.approve });
    const reject = screen.getByRole("button", { name: vi.memory.reject });
    await userEvent.click(approve);
    expect(approve).toBeDisabled();
    expect(reject).toBeDisabled();
    await userEvent.click(reject);

    release();
    await waitFor(() => expect(backend.proposals[0].status).toBe("approved"));
    expect(decisionPosts()).toHaveLength(1);
  });

  it("says a proposal was decided elsewhere, inline, and refreshes the list", async () => {
    backend.addProposal();
    mount(1);

    await open(vi.memory.proposals);
    const approve = await screen.findByRole("button", { name: vi.memory.approve });
    // Another tab rejects it after this one loaded the list.
    backend.proposals[0].status = "rejected";
    backend.proposals[0].resolved_at = "2026-09-20T08:30:00";
    await userEvent.click(approve);

    const notice = await screen.findByRole("status");
    expect(notice).toHaveTextContent(vi.memory.alreadyDecided);
    expect(screen.queryByRole("button", { name: vi.memory.approve })).toBeNull();
    // The refreshed list knows it was rejected, so the history counts it.
    expect(await screen.findByRole("button", { name: `${vi.memory.history} (1)` })).toBeInTheDocument();
    expect(notice).toHaveTextContent(vi.memory.proposalStatus.rejected);
    expect(screen.queryByText(vi.memory.decideFailed)).toBeNull();
  });

  it("shows a wiki compile as one card per page it would write", async () => {
    const pages = [
      { slug: "han-eco", kind: "entities", title: "Hạn Eco", body: "Hạn 30/9.", sources: ["2026-09-20"], questions: [], status: "ok" },
      { slug: "da-lat", kind: "concepts", title: "Đà Lạt", body: "Tháng 10.", sources: ["2026-09-21"], questions: [], status: "ok" },
    ];
    backend.addProposal({
      kind: "wiki_compile",
      name: "wiki",
      description: "2 trang",
      body: JSON.stringify(pages),
      previous_body: JSON.stringify([{ ...pages[0], body: "Hạn 25/9." }]),
    });
    mount(1);

    await open(vi.memory.proposals);
    const cards = within(await screen.findByRole("list", { name: vi.memory.compilePages(2) }));
    expect(cards.getAllByRole("listitem")).toHaveLength(2);
    expect(cards.getByText(vi.memory.compileUpdated)).toBeInTheDocument();
    expect(cards.getByText(vi.memory.compileNew)).toBeInTheDocument();
  });

  it("says so when undoing a rewrite fails, and confirms when it works", async () => {
    backend.setAgentMemory("default", { memory_md: "- b" });
    const rewrite = {
      kind: "agent_memory_rewrite",
      name: "MEMORY.md",
      description: "Cô đọng bộ nhớ",
      body: "- b",
      previous_body: "- a",
      status: "approved",
      resolved_at: "2026-09-20T09:00:00",
    } as const;
    // An agent that has since been removed: the server has nowhere to write the undo.
    backend.addProposal({ ...rewrite, agent_id: "gone" });
    backend.addProposal({ ...rewrite, description: "Cô đọng lần hai" });
    mount();

    await open(vi.memory.proposals);
    await userEvent.click(await screen.findByRole("button", { name: `${vi.memory.history} (2)` }));
    expect(screen.getAllByText(formatDateTime("2026-09-20T09:00:00"))).toHaveLength(2);
    vitest.spyOn(window, "confirm").mockReturnValue(true);
    const [gone, kept] = screen.getAllByRole("button", { name: vi.memory.undo });

    await userEvent.click(gone);
    expect(await screen.findByText(vi.memory.undoFailed)).toBeInTheDocument();

    await userEvent.click(kept);
    expect(await screen.findByText(vi.memory.undone)).toBeInTheDocument();
    expect(backend.readAgentMemory("default").memory_md).toBe("- a");
  });
});

describe("lineDiff", () => {
  it("shows the line a rewrite drops as well as the one it adds", () => {
    expect(lineDiff("a\n\nb", "a\nc")).toEqual([
      { text: "a", op: "same" },
      { text: "b", op: "remove" },
      { text: "c", op: "add" },
    ]);
  });
});
