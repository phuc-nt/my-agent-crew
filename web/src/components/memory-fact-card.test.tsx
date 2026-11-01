import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { FactInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { fakeAgent, FakeBackend } from "../test/fake-backend";
import { MemoryPanel } from "./memory-panel";

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  backend.agents = [fakeAgent];
  vitest.stubGlobal("fetch", backend.fetch);
});

const mount = () =>
  render(
    <MemoryPanel agents={backend.agents} agentId="default" pendingProposals={0} agentName={() => "Agent"} runs={[]} />,
  );

const fact = (overrides: Partial<FactInfo> = {}): FactInfo => ({
  name: "cong-ty",
  description: "Làm ở công ty A",
  type: "profile",
  written_by: "coach",
  source: "chat",
  updated: "2026-10-01T09:00:00",
  body: "Làm ở công ty A.",
  basis: "said",
  valid_from: "",
  valid_until: "",
  sources: ["conv:abc123", "job:daily"],
  version: 2,
  confirmed: "",
  stale: false,
  state: "current",
  recalls: 3,
  recalled_at: "2026-10-20T09:00:00",
  history_count: 1,
  ...overrides,
});

const card = async (name: string) => within(await screen.findByTestId(`fact-${name}`));

describe("the fact inspector", () => {
  it("says who stands behind a fact, its version, recalls and where it came from", async () => {
    backend.facts = [fact(), fact({ name: "gio-ngu", description: "Ngủ lúc 0h", basis: "inferred" })];
    mount();

    const said = await card("cong-ty");
    expect(said.getByText(vi.memory.factBasis.said)).toHaveClass("ok");
    expect(said.getByText(/v2/)).toBeInTheDocument();
    expect(said.getByText(new RegExp(vi.memory.factRecalls(3)))).toBeInTheDocument();
    expect(said.getByRole("link", { name: "conv:abc123" })).toHaveAttribute("href", "#/chat/abc123");
    expect(said.getByText("job:daily").tagName).toBe("CODE");
    const inferred = await card("gio-ngu");
    expect(inferred.getByText(vi.memory.factBasis.inferred)).not.toHaveClass("ok");
  });

  it("marks a fact that holds later and one past its last day", async () => {
    backend.facts = [
      fact({ name: "sap-toi", valid_from: "2026-12-01", state: "pending" }),
      fact({ name: "da-qua", valid_until: "2026-10-05", state: "expired" }),
    ];
    mount();

    const later = await card("sap-toi");
    expect(later.getByText(vi.memory.factPending("2026-12-01"))).toBeInTheDocument();
    expect(later.getByText(new RegExp(vi.memory.factSpan("2026-12-01", "")))).toBeInTheDocument();
    expect((await card("da-qua")).getByText(vi.memory.factExpired)).toBeInTheDocument();
  });

  it("an edit keeps the old version in a history that opens on demand", async () => {
    backend.facts = [fact({ version: 1, history_count: 0 })];
    mount();

    await userEvent.click((await card("cong-ty")).getByRole("button", { name: vi.memory.edit }));
    const body = screen.getByRole("textbox", { name: vi.memory.factBody });
    await userEvent.clear(body);
    await userEvent.type(body, "Làm ở công ty B.");
    await userEvent.type(screen.getByLabelText(vi.memory.validFrom), "2026-12-01");
    const form = body.closest("form")!;
    await userEvent.click(within(form).getByRole("button", { name: vi.memory.save }));

    await waitFor(() => expect(backend.facts[0].valid_from).toBe("2026-12-01"));
    const edited = await card("cong-ty");
    await userEvent.click(edited.getByRole("button", { name: vi.memory.factHistory(1) }));
    expect(await edited.findByText("Làm ở công ty A.")).toBeInTheDocument();
    expect(edited.getByText(new RegExp(vi.memory.factEnded.superseded))).toBeInTheDocument();
  });

  it("purges a fact and its history only after its own confirm", async () => {
    backend.facts = [fact()];
    const confirm = vitest.spyOn(window, "confirm").mockReturnValue(true);
    mount();

    await userEvent.click((await card("cong-ty")).getByRole("button", { name: vi.memory.purge }));

    expect(confirm).toHaveBeenCalledWith(vi.memory.confirmPurge("Làm ở công ty A"));
    await waitFor(() => expect(backend.facts).toEqual([]));
    expect(backend.factVersions.has("cong-ty")).toBe(false);
    expect(screen.queryByTestId("retracted-cong-ty")).toBeNull();
  });

  it("purges a retracted fact from the list of those taken back", async () => {
    backend.facts = [fact()];
    vitest.spyOn(window, "confirm").mockReturnValue(true);
    mount();

    await userEvent.click((await card("cong-ty")).getByRole("button", { name: vi.memory.retract }));
    const taken = within(await screen.findByTestId("retracted-cong-ty"));
    await userEvent.click(taken.getByRole("button", { name: vi.memory.purge }));

    await waitFor(() => expect(screen.queryByTestId("retracted-cong-ty")).toBeNull());
    expect(backend.factVersions.size).toBe(0);
  });
});
