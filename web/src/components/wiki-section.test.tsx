import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../i18n/vi";
import { coachAgent, fakeAgent, FakeBackend } from "../test/fake-backend";
import { WikiSection } from "./wiki-section";

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  backend.agents = [fakeAgent, coachAgent];
  vitest.stubGlobal("fetch", backend.fetch);
});

function mount(agentId = "default") {
  const onSelectAgent = vitest.fn();
  render(
    <WikiSection agents={backend.agents} agentId={agentId} onSelectAgent={onSelectAgent} />,
  );
  return onSelectAgent;
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

  it("saves an edited body back to the page", async () => {
    backend.wiki.add({ title: "Hạn Eco", body: "Thứ tư." });
    mount();
    await userEvent.click(await screen.findByRole("button", { name: "Hạn Eco" }));

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
    const { rerender } = render(
      <WikiSection agents={backend.agents} agentId="default" onSelectAgent={() => {}} />,
    );
    await userEvent.click(await screen.findByRole("button", { name: "Hạn Eco" }));
    await screen.findByTestId("wiki-page");

    backend.wiki.pages.clear();
    rerender(
      <WikiSection agents={backend.agents} agentId="coach" onSelectAgent={() => {}} />,
    );
    await waitFor(() => expect(screen.queryByTestId("wiki-page")).toBeNull());
  });
});
