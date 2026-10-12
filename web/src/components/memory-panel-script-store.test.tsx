import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../i18n/vi";
import { coachAgent, fakeAgent, FakeBackend } from "../test/fake-backend";
import { shownKeys, storeRequests } from "../test/script-store-screen";
import { MemoryPanel } from "./memory-panel";

let backend: FakeBackend;

beforeEach(() => {
  window.location.hash = "#/manage/memory";
  backend = new FakeBackend();
  backend.agents = [fakeAgent, coachAgent];
  backend.scriptStore.keep("default", "misc", "of-default", 1).keep("coach", "job:brief", "of-coach", 2);
  vitest.stubGlobal("fetch", backend.fetch);
});

afterEach(() => {
  window.location.hash = "";
});

/** The memory screen as the app shows it while the conversation is with the master. */
function mount(agents = backend.agents) {
  return render(<MemoryPanel agents={agents} agentId="default" pendingProposals={0} agentName={(id) => id} runs={[]} />);
}

const tab = (label: string) => screen.getByRole("tab", { name: label });
const storeTab = () => tab(vi.scriptStore.tab);
const agentSelect = () => screen.getByRole("combobox", { name: vi.agents });
const keysShown = (keys: string[]) => waitFor(() => expect(shownKeys()).toEqual(keys));

describe("the script store among the things the crew remembers", () => {
  it("has a tab of its own, after the wiki", () => {
    mount();

    expect(screen.getAllByRole("tab").map((one) => one.textContent)).toEqual([
      vi.memory.user,
      vi.memory.agents,
      vi.wiki.tab,
      vi.scriptStore.tab,
      vi.memory.search,
      vi.memory.proposals,
    ]);
    expect(storeTab()).toHaveAttribute("aria-selected", "false");
    expect(screen.queryByTestId("script-store")).toBeNull();
    expect(storeRequests(backend)).toEqual([]);
  });

  it("opens on the agent the screen is looking at, and writes that agent into the address", async () => {
    mount();

    await userEvent.click(storeTab());

    expect(storeTab()).toHaveAttribute("aria-selected", "true");
    expect(tab(vi.memory.user)).toHaveAttribute("aria-selected", "false");
    expect(window.location.hash).toBe("#/manage/memory/scripts/default");
    expect(agentSelect()).toHaveValue("default");
    await keysShown(["of-default"]);
    expect(storeRequests(backend)).toEqual(["GET /agents/default/script-store"]);
  });

  it("is opened by an address that names it, on the agent the address names", async () => {
    window.location.hash = "#/manage/memory/scripts/coach";
    mount();

    expect(storeTab()).toHaveAttribute("aria-selected", "true");
    expect(agentSelect()).toHaveValue("coach");
    await keysShown(["of-coach"]);
    expect(storeRequests(backend)).toEqual(["GET /agents/coach/script-store"]);
  });

  it("is opened on the screen's agent by an address that names no agent", async () => {
    window.location.hash = "#/manage/memory/scripts";
    mount();

    expect(agentSelect()).toHaveValue("default");
    await keysShown(["of-default"]);
  });

  it("falls back to the screen's agent for an agent the crew does not have, asking the server nothing about it", async () => {
    window.location.hash = "#/manage/memory/scripts/ghost";
    mount();

    expect(agentSelect()).toHaveValue("default");
    await keysShown(["of-default"]);
    expect(storeRequests(backend)).toEqual(["GET /agents/default/script-store"]);
  });

  // The page may be opened on a link before the crew has been read.
  it("takes the address at its word until the crew has been read", () => {
    window.location.hash = "#/manage/memory/scripts/coach";
    mount([]);

    expect(agentSelect()).toHaveValue("coach");
    expect(within(agentSelect()).getAllByRole("option").map((option) => option.textContent)).toEqual(["coach"]);
  });

  it("follows the agent chosen in it: the address names that agent and its keys replace the others", async () => {
    mount();
    await userEvent.click(storeTab());
    await keysShown(["of-default"]);

    await userEvent.selectOptions(agentSelect(), "coach");

    expect(window.location.hash).toBe("#/manage/memory/scripts/coach");
    expect(agentSelect()).toHaveValue("coach");
    await keysShown(["of-coach"]);
  });

  it("when left by another tab: the address stops naming it, and the agent looked at is the one the next tab shows", async () => {
    window.location.hash = "#/manage/memory/scripts/coach";
    mount();
    await keysShown(["of-coach"]);

    await userEvent.click(tab(vi.memory.agents));

    expect(window.location.hash).toBe("#/manage/memory");
    expect(tab(vi.memory.agents)).toHaveAttribute("aria-selected", "true");
    expect(storeTab()).toHaveAttribute("aria-selected", "false");
    expect(screen.queryByTestId("script-store")).toBeNull();
    expect(within(screen.getByTestId("memory-agent")).getByRole("combobox", { name: vi.agents })).toHaveValue("coach");

    // And back again on the same agent.
    await userEvent.click(storeTab());
    expect(window.location.hash).toBe("#/manage/memory/scripts/coach");
  });

  it("goes back to the tab the person came from when the browser does", async () => {
    mount();
    await userEvent.click(tab(vi.memory.agents));
    await userEvent.click(storeTab());
    expect(storeTab()).toHaveAttribute("aria-selected", "true");

    window.history.back();

    await waitFor(() => expect(tab(vi.memory.agents)).toHaveAttribute("aria-selected", "true"));
    expect(window.location.hash).toBe("#/manage/memory");
    expect(screen.queryByTestId("script-store")).toBeNull();
  });
});
