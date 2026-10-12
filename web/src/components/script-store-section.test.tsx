import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { parseRoute } from "../hooks/use-route";
import { vi } from "../i18n/vi";
import type { FakeBackend } from "../test/fake-backend";
import { BRIEF, holdRequests, mountStore, storeBackend, storeRequests } from "../test/script-store-screen";
import { formatDateTime } from "./run-timeline";

const { scriptStore: words } = vi;

let backend: FakeBackend;

beforeEach(() => {
  backend = storeBackend();
});

const cards = () => screen.findAllByTestId("script-store-namespace");
const card = async (namespace: string) => {
  const found = (await cards()).find((one) => one.dataset.namespace === namespace);
  if (!found) throw new Error(`no namespace ${namespace} on screen`);
  return found;
};
const keysOf = (held: HTMLElement) => [...held.querySelectorAll(".script-store-key")].map((key) => key.textContent);

describe("what an agent's scripts keep, listed", () => {
  it("names each namespace in words with a way to its owner, and keeps the stored name in sight", async () => {
    const chat = backend.create({ agent_id: "coach", title: "Đơn mới" });
    backend.scriptStore.keep("coach", "job:brief", "seen", ["a1", "b2"]).keep("coach", `conv:${chat.id}`, "draft", { note: "nháp" });
    mountStore(backend);

    expect((await cards()).map((one) => one.dataset.namespace)).toEqual([`conv:${chat.id}`, "job:brief"]);
    const job = await card("job:brief");
    expect(within(job).getByRole("heading")).toHaveTextContent(`${words.kinds.job}Bản tin sáng`);
    // A job's row among the jobs is named by its agent and its schedule.
    expect(parseRoute(within(job).getByRole("link", { name: "Bản tin sáng" }).getAttribute("href") as string)).toEqual({
      kind: "manage",
      section: "jobs",
      param: "coach/brief",
    });
    expect(within(job).getByText("job:brief")).toBeInTheDocument();

    const conv = await card(`conv:${chat.id}`);
    expect(within(conv).getByRole("heading")).toHaveTextContent(`${words.kinds.conv}Đơn mới`);
    expect(within(conv).getByRole("link", { name: "Đơn mới" })).toHaveAttribute("href", `#/chat/${chat.id}`);
    expect(within(conv).getByText(`conv:${chat.id}`)).toBeInTheDocument();
    expect(screen.queryByText(words.orphan)).toBeNull();
    expect(storeRequests(backend)).toEqual(["GET /agents/coach/script-store"]);
  });

  it("lists a namespace's keys in order, each with how its value opens, its size and when it was written", async () => {
    backend.scriptStore.keep("coach", "job:brief", "seen", ["a1", "b2"], "2026-10-11T23:40:00+00:00").keep("coach", "job:brief", "count", 2);
    mountStore(backend);

    const job = await card("job:brief");
    expect(keysOf(job)).toEqual(["count", "seen"]);
    const seen = within(job).getAllByTestId("script-store-entry")[1];
    expect(within(seen).getByTestId("script-store-preview")).toHaveTextContent('["a1","b2"]');
    expect(within(seen).getByText(words.entryChars(11), { exact: false })).toBeInTheDocument();
    // In the reader's own time, as the runs and the jobs are.
    const written = seen.querySelector("time") as HTMLTimeElement;
    expect(written).toHaveAttribute("datetime", "2026-10-11T23:40:00+00:00");
    expect(written).toHaveTextContent(formatDateTime("2026-10-11T23:40:00+00:00"));
  });

  it("measures a namespace against the most one holds, as a number and as a bar", async () => {
    backend.scriptStore.limitChars = 100;
    backend.scriptStore.keepText("coach", "job:brief", "k", "x".repeat(49));
    mountStore(backend);

    const job = await card("job:brief");
    expect(within(job).getByText(`${words.keyCount(1)} · ${words.size(50, 100)}`)).toBeInTheDocument();
    const bar = within(job).getByRole("progressbar", { name: words.sizeLabel(BRIEF) });
    expect(bar).toHaveAttribute("aria-valuenow", "50");
    expect(bar).toHaveClass("accent");
    expect(job.querySelector(".script-store-fill")).toBeNull();
  });

  it.each([
    ["nearly full", 79, "warn", words.nearLimit],
    ["full", 99, "danger", words.full],
  ])("warns in words and in the bar's colour when a namespace is %s", async (_, chars, tone, sentence) => {
    backend.scriptStore.limitChars = 100;
    backend.scriptStore.keepText("coach", "job:brief", "k", "x".repeat(chars));
    mountStore(backend);

    const job = await card("job:brief");
    expect(within(job).getByRole("progressbar")).toHaveClass(tone);
    expect(within(job).getByText(sentence)).toBeInTheDocument();
  });

  it("marks a namespace nothing reads any more, says it can be deleted, and offers no way to an owner that is gone", async () => {
    backend.scriptStore.keep("coach", "job:retired", "k", 1).keep("coach", "conv:deleted", "k", 1).keep("coach", "job:brief", "k", 1);
    mountStore(backend);

    const retired = await card("job:retired");
    expect(within(retired).getByText(words.orphan)).toBeInTheDocument();
    expect(within(retired).getByText(words.orphanHint.job)).toBeInTheDocument();
    expect(within(retired).getByRole("heading")).toHaveTextContent(`${words.kinds.job}retired`);
    expect(within(retired).queryByRole("link")).toBeNull();
    expect(within(retired).getByText("job:retired")).toBeInTheDocument();
    expect(within(await card("conv:deleted")).getByText(words.orphanHint.conv)).toBeInTheDocument();

    const live = await card("job:brief");
    expect(within(live).queryByText(words.orphan)).toBeNull();
    expect(live.querySelector(".script-store-orphan-hint")).toBeNull();
  });

  it("names a namespace that is neither a schedule's nor a conversation's by its stored name, once", async () => {
    backend.scriptStore.keep("coach", "misc", "k", 1);
    mountStore(backend);

    const misc = await card("misc");
    expect(within(misc).getByRole("heading")).toHaveTextContent(`${words.kinds.other}misc`);
    expect(within(misc).getAllByText("misc")).toHaveLength(1);
    expect(within(misc).queryByRole("link")).toBeNull();
  });

  it("shows what an older server sends: the stored name, a size with no limit, no mark and no bar", async () => {
    backend.scriptStore.old = true;
    backend.scriptStore.keep("coach", "job:retired", "seen", ["a1"]);
    mountStore(backend);

    const job = await card("job:retired");
    expect(within(job).getByRole("heading")).toHaveTextContent(/^job:retired$/);
    expect(within(job).getAllByText("job:retired")).toHaveLength(1);
    expect(within(job).getByText(`${words.keyCount(1)} · ${words.sizeAlone(10)}`)).toBeInTheDocument();
    expect(within(job).queryByRole("progressbar")).toBeNull();
    expect(within(job).queryByRole("link")).toBeNull();
    expect(within(job).queryByText(words.orphan)).toBeNull();
    // Its keys still open and can still be deleted.
    await userEvent.click(within(job).getByRole("button", { name: words.viewLabel("seen") }));
    expect(await within(job).findByRole("group", { name: words.valueLabel("seen") })).toHaveTextContent('[ "a1" ]');
    expect(within(job).getByRole("button", { name: words.deleteAllLabel('"job:retired"') })).toBeEnabled();
  });

  it("says in one sentence what this is when the agent's scripts kept nothing", async () => {
    mountStore(backend);

    expect(await screen.findByTestId("empty-state")).toHaveTextContent(words.empty);
    expect(screen.queryByText(vi.loading)).toBeNull();
    expect(screen.queryByTestId("script-store-namespace")).toBeNull();
    expect(screen.getByText(words.intro)).toBeInTheDocument();
  });

  it("says it is reading until the list has come, and not that there is nothing", async () => {
    const release = holdRequests(backend, /^GET .*\/script-store$/);
    mountStore(backend);

    expect(screen.getByText(vi.loading)).toBeInTheDocument();
    expect(screen.queryByTestId("empty-state")).toBeNull();
    release();
    expect(await screen.findByTestId("empty-state")).toBeInTheDocument();
    expect(screen.queryByText(vi.loading)).toBeNull();
  });

  it("shows the usual error when the list cannot be read, and reads it again when asked", async () => {
    backend.scriptStore.keep("coach", "job:brief", "k", 1);
    backend.scriptStore.refuse.list = { status: 500, detail: "boom" };
    mountStore(backend);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(vi.requestErrors.server(500));
    expect(screen.queryByText(vi.loading)).toBeNull();
    expect(screen.queryByTestId("empty-state")).toBeNull();

    backend.scriptStore.refuse = {};
    await userEvent.click(within(alert).getByRole("button", { name: vi.retry }));
    expect(await card("job:brief")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("offers the crew's agents, and tells its owner which one was chosen", async () => {
    const { onSelectAgent } = mountStore(backend);

    const select = screen.getByRole("combobox", { name: vi.agents });
    expect(select).toHaveValue("coach");
    expect(within(select).getAllByRole("option").map((option) => option.textContent)).toEqual(["Agent", "HLV sức khoẻ"]);
    await userEvent.selectOptions(select, "default");
    expect(onSelectAgent).toHaveBeenCalledWith("default");
  });

  it("never shows one agent's keys under the next agent's name", async () => {
    backend.scriptStore.keep("coach", "job:brief", "of-coach", 1).keep("default", "misc", "of-default", 2);
    const { show } = mountStore(backend);
    await card("job:brief");

    const release = holdRequests(backend, /^GET .*\/agents\/default\/script-store$/);
    show("default");
    expect(screen.queryByTestId("script-store-namespace")).toBeNull();
    expect(screen.getByText(vi.loading)).toBeInTheDocument();
    release();
    expect(keysOf(await card("misc"))).toEqual(["of-default"]);
    expect(screen.queryByText("of-coach")).toBeNull();
  });
});
