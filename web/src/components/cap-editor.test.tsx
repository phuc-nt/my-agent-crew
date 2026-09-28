import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { api } from "../api/client";
import { vi } from "../i18n/vi";
import { FakeBackend } from "../test/fake-backend";
import { BudgetIndicator } from "./budget-indicator";
import { CapEditor } from "./cap-editor";

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  backend.create({ cost_cap_usd: 1 });
  vitest.stubGlobal("fetch", backend.fetch);
});

const saveToServer = async (cost_cap_usd: number) => {
  await api.patchConversation("c1", { cost_cap_usd });
};
const patches = () => backend.requests.filter((r) => r.method === "PATCH").map((r) => r.body);

describe("CapEditor", () => {
  it("raises the cap by a step above the current one", async () => {
    render(<CapEditor capUsd={1} onSave={saveToServer} />);
    expect(screen.getByTestId("cap-editor")).toHaveTextContent(`${vi.budgetCard.cap} $1.00`);

    await userEvent.click(screen.getByRole("button", { name: "+$0.50" }));
    await userEvent.click(screen.getByRole("button", { name: "+$1.00" }));
    await waitFor(() => expect(patches()).toEqual([{ cost_cap_usd: 1.5 }, { cost_cap_usd: 2 }]));
  });

  // 0.1 + 0.5 is 0.6000000000000001 in floating point: the cap sent is the cents shown.
  it("sends a stepped cap in whole cents", async () => {
    render(<CapEditor capUsd={0.1} onSave={saveToServer} />);
    await userEvent.click(screen.getByRole("button", { name: "+$0.50" }));
    await waitFor(() => expect(patches()).toEqual([{ cost_cap_usd: 0.6 }]));
  });

  it("takes a typed 0 as no cap at all", async () => {
    render(<CapEditor capUsd={1} onSave={saveToServer} />);
    await userEvent.type(screen.getByLabelText(vi.budgetCard.custom), "0{Enter}");
    await waitFor(() => expect(patches()).toEqual([{ cost_cap_usd: 0 }]));
    expect(backend.conversations.get("c1")!.cost_cap_usd).toBe(0);
  });

  it("refuses a negative cap without asking the server", async () => {
    render(<CapEditor capUsd={1} onSave={saveToServer} />);
    await userEvent.type(screen.getByLabelText(vi.budgetCard.custom), "-1");
    await userEvent.click(screen.getByRole("button", { name: vi.budgetCard.set }));
    expect(screen.getByRole("alert")).toHaveTextContent(vi.budgetCard.capInvalid);
    expect(patches()).toEqual([]);
  });

  // What FastAPI sends for a value its model refuses: a list of failures, not a sentence.
  const validationDump = JSON.stringify([
    { type: "greater_than_equal", loc: ["body", "cost_cap_usd"], msg: "Input should be greater than or equal to 0" },
  ]);

  it("says in words why the server refused a cap, not in its validation dump", async () => {
    backend.refuseEdit = validationDump;
    render(<CapEditor capUsd={1} onSave={saveToServer} />);
    await userEvent.click(screen.getByRole("button", { name: "+$1.00" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(vi.budgetCard.saveFailed(vi.requestErrors.invalid));
  });

  it("keeps a refusal the server wrote as a sentence", async () => {
    backend.refuseEdit = "Trần chi phí vượt mức cho phép của máy chủ.";
    render(<CapEditor capUsd={1} onSave={saveToServer} />);
    await userEvent.click(screen.getByRole("button", { name: "+$1.00" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      vi.budgetCard.saveFailed("Trần chi phí vượt mức cho phép của máy chủ."),
    );
  });

  it("says the conversation is gone when the server no longer has it", async () => {
    render(<CapEditor capUsd={1} onSave={(cap) => api.patchConversation("gone", { cost_cap_usd: cap }).then(() => {})} />);
    await userEvent.click(screen.getByRole("button", { name: "+$1.00" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(vi.budgetCard.saveFailed(vi.budgetCard.gone));
  });

  it("says the server could not be reached rather than the browser's own words", async () => {
    vitest.stubGlobal("fetch", () => Promise.reject(new TypeError("Failed to fetch")));
    render(<CapEditor capUsd={1} onSave={saveToServer} />);
    await userEvent.click(screen.getByRole("button", { name: "+$1.00" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(vi.budgetCard.saveFailed(vi.requestErrors.network));
  });

  // A disabled button drops the keyboard's focus onto the page, so a save on its way holds
  // the controls off without disabling them.
  it("keeps a pressed step focusable while its save is on its way, and saves it once", async () => {
    let finish = () => {};
    const onSave = vitest.fn(() => new Promise<void>((resolve) => (finish = resolve)));
    render(<CapEditor capUsd={1} onSave={onSave} />);
    const step = screen.getByRole("button", { name: "+$0.50" });
    await userEvent.click(step);
    expect(step).toHaveFocus();
    expect(step).toBeEnabled();
    expect(step).toHaveAttribute("aria-disabled", "true");

    await userEvent.click(step);
    expect(onSave).toHaveBeenCalledTimes(1);
    await act(async () => finish());
    expect(step).not.toHaveAttribute("aria-disabled");
    expect(step).toHaveFocus();
  });

  it("keeps Set focusable once its save empties the field, and sends nothing from an empty one", async () => {
    render(<CapEditor capUsd={1} onSave={saveToServer} />);
    await userEvent.type(screen.getByLabelText(vi.budgetCard.custom), "3");
    const set = screen.getByRole("button", { name: vi.budgetCard.set });
    await userEvent.click(set);
    await waitFor(() => expect(patches()).toEqual([{ cost_cap_usd: 3 }]));
    expect(screen.getByLabelText(vi.budgetCard.custom)).toHaveValue(null);
    expect(set).toHaveFocus();
    expect(set).toBeEnabled();
    expect(set).toHaveAttribute("aria-disabled", "true");

    await userEvent.click(set);
    expect(patches()).toEqual([{ cost_cap_usd: 3 }]);
  });

  // Stepping up from no cap at all would put one in place, the opposite of raising it.
  it("offers no steps while the cap is lifted", () => {
    render(<CapEditor capUsd={0} onSave={saveToServer} />);
    expect(screen.getByTestId("cap-editor")).toHaveTextContent(vi.unlimited);
    expect(screen.queryByRole("group", { name: vi.budgetCard.raise })).not.toBeInTheDocument();
  });

  it("sits in the budget card when the cap can be changed", async () => {
    const { rerender } = render(<BudgetIndicator spentUsd={0.25} capUsd={1} unknownCostCalls={0} />);
    await userEvent.click(screen.getByTestId("budget"));
    expect(screen.queryByTestId("cap-editor")).not.toBeInTheDocument();

    rerender(<BudgetIndicator spentUsd={0.25} capUsd={1} unknownCostCalls={0} onSetCap={saveToServer} />);
    const card = screen.getByRole("dialog", { name: vi.budgetCard.title });
    await userEvent.click(within(card).getByRole("button", { name: "+$0.50" }));
    await waitFor(() => expect(patches()).toEqual([{ cost_cap_usd: 1.5 }]));
  });
});
