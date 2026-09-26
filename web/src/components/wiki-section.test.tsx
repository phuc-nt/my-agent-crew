import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { api } from "../api/client";
import type { RunInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { coachAgent, fakeAgent, FakeBackend, fakeRun } from "../test/fake-backend";
import { runOutcome } from "./run-chip";
import { WikiSection } from "./wiki-section";

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  backend.agents = [fakeAgent, coachAgent];
  vitest.stubGlobal("fetch", backend.fetch);
});

afterEach(() => {
  vitest.useRealTimers();
  vitest.restoreAllMocks();
});

/** The section as the memory panel mounts it, with notes going through the real client. */
function section(agentId = "default", runs: RunInfo[] = []) {
  return (
    <WikiSection
      agents={backend.agents}
      agentId={agentId}
      runs={runs}
      onSelectAgent={() => {}}
      onReadNote={async (day) => (await api.getNote(agentId, day)).body}
      onSaveNote={async (day, body) => {
        await api.putNote(agentId, day, body);
      }}
    />
  );
}

function mount(agentId = "default", runs: RunInfo[] = []) {
  return render(section(agentId, runs));
}

describe("WikiSection", () => {
  it("tells the person how the vault gets filled when there is nothing in it", async () => {
    mount();
    expect(await screen.findByText(vi.wiki.empty)).toBeInTheDocument();
  });

  it("groups the pages under the kind they are filed as", async () => {
    backend.wiki.add({ slug: "han-eco", title: "Hạn Eco", kind: "entities" });
    backend.wiki.add({ slug: "tra-sang", title: "Trà sáng", kind: "concepts" });
    mount();

    expect(await screen.findByRole("heading", { name: vi.wiki.kinds.entities })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: vi.wiki.kinds.concepts })).toBeInTheDocument();
    expect(screen.getByText(vi.wiki.count(2))).toBeInTheDocument();
  });

  it("marks a page with no evidence behind it, because that is the one to go fix", async () => {
    backend.wiki.add({ title: "Hạn Eco", sources: [] });
    mount();
    expect(await screen.findByText(vi.wiki.noSources)).toBeInTheDocument();
  });

  it("narrows the list to what was searched for", async () => {
    backend.wiki.add({ slug: "han-eco", title: "Hạn Eco" });
    backend.wiki.add({ slug: "tra-sang", title: "Trà sáng", kind: "concepts" });
    mount();
    await screen.findByRole("button", { name: "Trà sáng" });

    await userEvent.type(screen.getByRole("searchbox", { name: vi.wiki.searchPlaceholder }), "Trà");
    await waitFor(() => expect(screen.queryByRole("button", { name: "Hạn Eco" })).toBeNull());
    expect(screen.getByRole("button", { name: "Trà sáng" })).toBeInTheDocument();
  });

  it("says a search found nothing rather than that the vault is empty", async () => {
    backend.wiki.add({ title: "Hạn Eco" });
    mount();
    await screen.findByRole("button", { name: "Hạn Eco" });

    await userEvent.type(screen.getByRole("searchbox", { name: vi.wiki.searchPlaceholder }), "xyz");
    expect(await screen.findByText(vi.wiki.searchEmpty)).toBeInTheDocument();
  });

  it("opens a page with its body, which the list never carried", async () => {
    backend.wiki.add({ title: "Hạn Eco", body: "Hạn nộp hồ sơ là thứ tư." });
    mount();

    await userEvent.click(await screen.findByRole("button", { name: "Hạn Eco" }));
    const page = await screen.findByTestId("wiki-page");
    expect(page).toHaveTextContent("Hạn nộp hồ sơ là thứ tư.");
    expect(page).toHaveTextContent("note:2026-09-19");
  });

  it("saves an edited body back to the page, once switched from reading to editing", async () => {
    backend.wiki.add({ title: "Hạn Eco", body: "Thứ tư." });
    mount();
    await userEvent.click(await screen.findByRole("button", { name: "Hạn Eco" }));
    expect(screen.queryByRole("textbox", { name: new RegExp(vi.wiki.body) })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: vi.memory.edit }));

    const textarea = await screen.findByRole("textbox", { name: new RegExp(vi.wiki.body) });
    await userEvent.type(textarea, " Đã dời một lần.");
    await userEvent.click(screen.getByRole("button", { name: vi.memory.save }));

    await waitFor(() =>
      expect(backend.wiki.pages.get("han-eco")?.body).toBe("Thứ tư. Đã dời một lần."),
    );
  });

  it("does not delete a page when the confirm is dismissed", async () => {
    backend.wiki.add({ title: "Hạn Eco" });
    vitest.spyOn(window, "confirm").mockReturnValue(false);
    mount();
    await userEvent.click(await screen.findByRole("button", { name: "Hạn Eco" }));

    await userEvent.click(screen.getByRole("button", { name: vi.memory.remove }));
    expect(backend.wiki.pages.has("han-eco")).toBe(true);
  });

  it("returns to the list after a confirmed delete, with the page gone", async () => {
    backend.wiki.add({ title: "Hạn Eco" });
    vitest.spyOn(window, "confirm").mockReturnValue(true);
    mount();
    await userEvent.click(await screen.findByRole("button", { name: "Hạn Eco" }));

    await userEvent.click(screen.getByRole("button", { name: vi.memory.remove }));
    expect(await screen.findByText(vi.wiki.empty)).toBeInTheDocument();
    expect(backend.wiki.pages.has("han-eco")).toBe(false);
  });

  it("shows what the lint found, so a broken vault is visible without opening a page", async () => {
    backend.wiki.add({ title: "Hạn Eco" });
    backend.wiki.problems = [
      { slug: "han-eco", kind: "dangling", detail: "[[Trà sáng]]" },
    ];
    mount();

    expect(await screen.findByText(new RegExp(vi.wiki.problemKinds.dangling))).toBeInTheDocument();
    expect(screen.queryByText(vi.wiki.problemsEmpty)).toBeNull();
  });

  it("starts a compile and says where to watch it", async () => {
    mount();
    await screen.findByText(vi.wiki.empty);

    await userEvent.click(screen.getByRole("button", { name: vi.wiki.compile }));
    expect(await screen.findByText(vi.wiki.compileStarted)).toBeInTheDocument();
    expect(backend.wiki.compiled).toEqual(["default"]);
  });

  it("explains a refused compile as the agent being busy, not as a failure", async () => {
    backend.wiki.busy = true;
    mount();
    await screen.findByText(vi.wiki.empty);

    await userEvent.click(screen.getByRole("button", { name: vi.wiki.compile }));
    expect(await screen.findByText(vi.wiki.compileBusy)).toBeInTheDocument();
  });

  it("does not leave one agent's page on screen after switching to another", async () => {
    backend.wiki.add({ title: "Hạn Eco" });
    const { rerender } = mount("default");
    await userEvent.click(await screen.findByRole("button", { name: "Hạn Eco" }));
    await screen.findByTestId("wiki-page");

    backend.wiki.pages.clear();
    rerender(section("coach"));
    await waitFor(() => expect(screen.queryByTestId("wiki-page")).toBeNull());
  });
});

describe("WikiSection read mode", () => {
  it("opens a page rendered as prose rather than as the raw text box", async () => {
    backend.wiki.add({ title: "Hạn Eco", body: "Hạn nộp là **thứ tư**." });
    mount();
    await userEvent.click(await screen.findByRole("button", { name: "Hạn Eco" }));

    const page = await screen.findByTestId("wiki-page");
    expect(within(page).getByText("thứ tư").tagName).toBe("STRONG");
    expect(within(page).queryByRole("textbox")).toBeNull();
    expect(page).not.toHaveTextContent("**");
  });

  it("follows a [[link]] to the page it names", async () => {
    backend.wiki.add({ title: "Hạn Eco", body: "Pha [[Trà sáng]] trước khi nộp." });
    backend.wiki.add({ slug: "tra-sang", title: "Trà sáng", kind: "concepts", body: "Pha lúc 6h." });
    mount();
    await userEvent.click(await screen.findByRole("button", { name: "Hạn Eco" }));

    const page = await screen.findByTestId("wiki-page");
    await userEvent.click(within(page).getByRole("button", { name: "Trà sáng" }));
    expect(await screen.findByRole("heading", { name: "Trà sáng" })).toBeInTheDocument();
    expect(screen.getByTestId("wiki-page")).toHaveTextContent("Pha lúc 6h.");
  });

  it("still follows a link to a page the search has left out of the list", async () => {
    backend.wiki.add({ title: "Hạn Eco", body: "Pha [[Trà sáng]] trước khi nộp." });
    backend.wiki.add({ slug: "tra-sang", title: "Trà sáng", kind: "concepts", body: "Pha lúc 6h." });
    mount();
    await screen.findByRole("button", { name: "Trà sáng" });
    await userEvent.type(screen.getByRole("searchbox", { name: vi.wiki.searchPlaceholder }), "Eco");
    await waitFor(() => expect(screen.queryByRole("button", { name: "Trà sáng" })).toBeNull());

    await userEvent.click(screen.getByRole("button", { name: "Hạn Eco" }));
    const page = await screen.findByTestId("wiki-page");
    await userEvent.click(within(page).getByRole("button", { name: "Trà sáng" }));
    expect(await screen.findByRole("heading", { name: "Trà sáng" })).toBeInTheDocument();
  });

  it("draws a link to a page nobody has written as missing, not as a way somewhere", async () => {
    backend.wiki.add({ title: "Hạn Eco", body: "Hỏi [[Đà Lạt]] sau." });
    mount();
    await userEvent.click(await screen.findByRole("button", { name: "Hạn Eco" }));

    const page = await screen.findByTestId("wiki-page");
    expect(within(page).queryByRole("button", { name: /Đà Lạt/ })).toBeNull();
    const missing = within(page).getByText("Đà Lạt");
    expect(missing).toHaveClass("wiki-link", "missing");
    expect(missing).toHaveTextContent(vi.wiki.missingLink);
  });

  it("marks a page as fine with a status-only PUT and updates the badge in place", async () => {
    backend.wiki.add({ title: "Hạn Eco", status: "review" });
    mount();
    await userEvent.click(await screen.findByRole("button", { name: "Hạn Eco" }));
    expect(await screen.findByTestId("wiki-status")).toHaveTextContent(vi.wiki.needsReview);

    await userEvent.click(screen.getByRole("button", { name: vi.wiki.markOk }));
    await waitFor(() => expect(screen.getByTestId("wiki-status")).toHaveTextContent(vi.wiki.statusOk));
    expect(backend.wiki.edits).toEqual([{ slug: "han-eco", body: { status: "ok" } }]);
    expect(screen.queryByRole("button", { name: vi.wiki.markOk })).toBeNull();
    expect(screen.getByTestId("wiki-page")).toBeInTheDocument();
  });

  it("does not call a mark-ok failed when only the list re-read after it fails", async () => {
    backend.wiki.add({ title: "Hạn Eco", status: "review" });
    const fetchThrough = backend.fetch;
    let listDown = false;
    let refused = 0;
    vitest.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) => {
      const list = new URL(String(input), "http://fake").pathname.endsWith("/memory/wiki");
      if (!listDown || !list) return fetchThrough(input, init);
      refused += 1;
      return Promise.resolve(new Response(JSON.stringify({ detail: "down" }), { status: 500 }));
    });
    mount();
    await userEvent.click(await screen.findByRole("button", { name: "Hạn Eco" }));

    listDown = true;
    await userEvent.click(await screen.findByRole("button", { name: vi.wiki.markOk }));
    await waitFor(() => expect(refused).toBe(1));
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(screen.getByTestId("wiki-status")).toHaveTextContent(vi.wiki.statusOk);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("says a failed mark-ok did not land, and leaves that failure behind on the next page", async () => {
    backend.wiki.add({ title: "Hạn Eco", status: "review", body: "Xem [[Trà sáng]]." });
    backend.wiki.add({ slug: "tra-sang", title: "Trà sáng", kind: "concepts", status: "review" });
    const fetchThrough = backend.fetch;
    vitest.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) =>
      init?.method === "PUT"
        ? Promise.resolve(new Response(JSON.stringify({ detail: "down" }), { status: 500 }))
        : fetchThrough(input, init),
    );
    mount();
    await userEvent.click(await screen.findByRole("button", { name: "Hạn Eco" }));

    await userEvent.click(await screen.findByRole("button", { name: vi.wiki.markOk }));
    expect(await screen.findByRole("alert")).toHaveTextContent(vi.wiki.markOkFailed);
    expect(screen.getByTestId("wiki-status")).toHaveTextContent(vi.wiki.needsReview);
    expect(screen.getByRole("button", { name: vi.wiki.markOk })).toBeEnabled();

    await userEvent.click(within(screen.getByTestId("wiki-page")).getByRole("button", { name: "Trà sáng" }));
    expect(await screen.findByRole("heading", { name: "Trà sáng" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("gathers every page's open questions and leads to the page that asked", async () => {
    backend.wiki.add({ title: "Hạn Eco", questions: ["Dời sang thứ năm được không?"] });
    backend.wiki.add({ slug: "tra-sang", title: "Trà sáng", kind: "concepts", questions: ["Mấy độ?"] });
    mount();

    const toggle = await screen.findByRole("button", { name: vi.wiki.openQuestions(2) });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const list = screen.getByRole("region", { name: vi.wiki.openQuestions(2) });
    expect(list).toHaveTextContent("Dời sang thứ năm được không?");
    expect(list).toHaveTextContent("Mấy độ?");
    await userEvent.click(within(list).getByRole("button", { name: "Trà sáng" }));
    expect(await screen.findByRole("heading", { name: "Trà sáng" })).toBeInTheDocument();
  });

  it("lists a question a page asked twice as two rows, in the vault list and on the page", async () => {
    // Nothing on the server folds a repeated question, and a model does repeat itself.
    backend.wiki.add({ title: "Hạn Eco", questions: ["Mấy giờ?", "Mấy giờ?"] });
    const errors = vitest.spyOn(console, "error").mockImplementation(() => undefined);
    mount();

    await userEvent.click(await screen.findByRole("button", { name: vi.wiki.openQuestions(2) }));
    const list = screen.getByRole("region", { name: vi.wiki.openQuestions(2) });
    expect(within(list).getAllByText("Mấy giờ?")).toHaveLength(2);
    await userEvent.click(within(list).getAllByRole("button", { name: "Hạn Eco" })[0]);
    expect(within(await screen.findByTestId("wiki-page")).getAllByText("Mấy giờ?")).toHaveLength(2);
    // React reports a repeated list key here; such a list can drop or repeat rows on update.
    expect(errors).not.toHaveBeenCalled();
  });

  it("offers no open-questions list when the vault has none", async () => {
    backend.wiki.add({ title: "Hạn Eco" });
    mount();
    await screen.findByRole("button", { name: "Hạn Eco" });

    expect(screen.queryByRole("button", { name: /Câu hỏi mở/ })).toBeNull();
    expect(screen.getByRole("button", { name: vi.wiki.todayNote })).toBeInTheDocument();
  });

  it("writes today's note under the viewer's own date, not the UTC one", async () => {
    // 01:30 on the 26th in Hà Nội is still the 25th in UTC.
    vitest.useFakeTimers({ toFake: ["Date"] });
    vitest.setSystemTime(new Date("2026-09-25T18:30:00Z"));
    mount();

    await userEvent.click(await screen.findByRole("button", { name: vi.wiki.todayNote }));
    const note = await screen.findByRole("textbox", { name: vi.wiki.todayNoteLabel("2026-09-26") });
    await userEvent.type(note, "Hỏi lại hạn Eco.");
    await userEvent.click(screen.getByRole("button", { name: vi.memory.save }));

    await waitFor(() => expect(backend.notes.get("default/2026-09-26")).toBe("Hỏi lại hạn Eco."));
  });

  it("says today's note could not be read instead of offering an empty one to overwrite", async () => {
    render(
      <WikiSection
        agents={backend.agents}
        agentId="default"
        runs={[]}
        onSelectAgent={() => {}}
        onReadNote={() => Promise.reject(new Error("offline"))}
        onSaveNote={async () => {}}
      />,
    );

    await userEvent.click(await screen.findByRole("button", { name: vi.wiki.todayNote }));
    expect(await screen.findByRole("alert")).toHaveTextContent(vi.loadFailed);
    expect(screen.queryByRole("textbox", { name: /Ghi chú/ })).toBeNull();
  });
});

describe("WikiSection compile tracking", () => {
  const compileRun = (over: Partial<RunInfo>) =>
    fakeRun({ id: "wiki-1", source: "memory:wiki", conversation_id: null, status: "running", ...over });

  it("follows the compile it started until the run ends, then reloads the list", async () => {
    // A compile that finished earlier must not count as the one just started.
    const earlier = compileRun({ id: "wiki-0", status: "done" });
    const { rerender } = mount("default", [earlier]);
    await screen.findByText(vi.wiki.empty);

    await userEvent.click(screen.getByRole("button", { name: vi.wiki.compile }));
    const chip = await screen.findByRole("status");
    expect(chip).toHaveTextContent(vi.wiki.compileStarted);
    expect(screen.getByRole("button", { name: vi.wiki.compile })).toBeDisabled();

    rerender(section("default", [earlier, compileRun({})]));
    expect(await screen.findByText(vi.runStatus.running)).toBeInTheDocument();

    backend.wiki.add({ title: "Hạn Eco" });
    const finished = compileRun({ status: "done", summary: "Đề xuất 1 trang." });
    rerender(section("default", [earlier, finished]));

    expect(await screen.findByRole("button", { name: "Hạn Eco" })).toBeInTheDocument();
    expect(screen.getByText(runOutcome(finished))).toBeInTheDocument();
    expect(screen.queryByText(vi.wiki.compileStarted)).toBeNull();
    expect(screen.getByRole("button", { name: vi.wiki.compile })).toBeEnabled();
  });

  it("does not stop following for a finished run that is not the one it started", async () => {
    const { rerender } = mount("default", []);
    await screen.findByText(vi.wiki.empty);

    await userEvent.click(screen.getByRole("button", { name: vi.wiki.compile }));
    await screen.findByText(vi.wiki.compileStarted);
    // Another agent's compile, and a chat run, finishing meanwhile are not this one either.
    rerender(section("default", [compileRun({ id: "coach-1", agent_id: "coach", status: "done" }), fakeRun()]));
    expect(await screen.findByText(vi.wiki.compileStarted)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: vi.wiki.compile })).toBeDisabled();
  });

  it("says how the compile ended in the same live region that showed it running", async () => {
    const { rerender } = mount("default", []);
    await screen.findByText(vi.wiki.empty);
    // A screen reader announces changes to a region it already knows, not a new one.
    const region = screen.getByRole("status");

    await userEvent.click(screen.getByRole("button", { name: vi.wiki.compile }));
    await waitFor(() => expect(region).toHaveTextContent(vi.wiki.compileStarted));
    const finished = compileRun({ status: "error", summary: "Hết hạn mức." });
    rerender(section("default", [finished]));

    await waitFor(() => expect(region).toHaveTextContent(runOutcome(finished)));
    expect(screen.getByRole("status")).toBe(region);
  });

  it("says a compile is busy in the live region too", async () => {
    backend.wiki.busy = true;
    mount();
    await screen.findByText(vi.wiki.empty);

    await userEvent.click(screen.getByRole("button", { name: vi.wiki.compile }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(vi.wiki.compileBusy));
  });

  it("keeps a compile's outcome with the agent it ran for once the person has moved on", async () => {
    const coachReads = () =>
      backend.requests.filter((r) => r.method === "GET" && r.path.startsWith("/agents/coach/memory/wiki")).length;
    const { rerender } = mount("default", []);
    await screen.findByText(vi.wiki.empty);
    await userEvent.click(screen.getByRole("button", { name: vi.wiki.compile }));
    await screen.findByText(vi.wiki.compileStarted);

    rerender(section("coach", []));
    await waitFor(() => expect(coachReads()).toBe(2));
    const finished = compileRun({ status: "done", summary: "Đề xuất 1 trang." });
    rerender(section("coach", [finished]));

    // The coach's vault did not change, so it is neither re-read nor captioned with this.
    await waitFor(() => expect(screen.getByRole("button", { name: vi.wiki.compile })).toBeEnabled());
    expect(screen.queryByText(runOutcome(finished))).toBeNull();
    expect(coachReads()).toBe(2);
    rerender(section("default", [finished]));
    expect(await screen.findByText(runOutcome(finished))).toBeInTheDocument();
  });
});
