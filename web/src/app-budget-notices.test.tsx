import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { App } from "./app";
import { vi } from "./i18n/vi";
import { FakeBackend, FakeEventSource, fakeRun } from "./test/fake-backend";

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  FakeEventSource.instances = [];
  vitest.stubGlobal("fetch", backend.fetch);
  vitest.stubGlobal("EventSource", FakeEventSource);
  window.location.hash = "";
});

afterEach(() => vitest.unstubAllGlobals());

function stream(): FakeEventSource {
  const source = FakeEventSource.instances.at(-1);
  if (!source) throw new Error("the app has not subscribed to the activity stream");
  return source;
}

const raiseButtons = () => screen.queryAllByRole("button", { name: vi.budgetCard.raise });

/** Opens a conversation at its cap and sends the turn the budget halts. */
async function haltOnBudget() {
  const c = backend.create({ title: "Hết tiền" });
  backend.nextTurn = [{ type: "halted", reason: "budget", spent_usd: 1 }];
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: /Hết tiền/ }));
  act(() => {
    stream().open();
    stream().emit({ type: "snapshot", runs: [] });
  });
  await userEvent.type(screen.getByRole("textbox"), "tiếp{Enter}");
  const halted = await screen.findByTestId("notice");
  expect(halted).toHaveTextContent(vi.haltedBudget);
  // What the server keeps once the turn halts; the list learns it when the run's end
  // comes down the stream.
  c.spent_usd = 1;
  c.over_budget = true;
  return halted;
}

describe("the budget notices", () => {
  it("offer the raise on one notice at a time, and the halt lets go of it once the cap is raised", async () => {
    const halted = await haltOnBudget();
    expect(within(halted).getByRole("button", { name: vi.budgetCard.raise })).toBeInTheDocument();

    act(() => stream().emit({ type: "run", run: fakeRun({ status: "halted" }) }));
    const over = await screen.findByTestId("over-budget");
    expect(raiseButtons()).toEqual([within(over).getByRole("button", { name: vi.budgetCard.raise })]);

    await userEvent.click(within(over).getByRole("button", { name: vi.budgetCard.raise }));
    await userEvent.click(within(over).getByRole("button", { name: "+$1.00" }));
    await waitFor(() => expect(screen.queryByTestId("over-budget")).not.toBeInTheDocument());
    expect(screen.getByTestId("notice")).toHaveTextContent(vi.haltedBudgetLifted);
    expect(raiseButtons()).toEqual([]);
  });

  it("let the halt's notice say the new cap is saved and the message wants sending again", async () => {
    const halted = await haltOnBudget();
    await userEvent.click(within(halted).getByRole("button", { name: vi.budgetCard.raise }));
    await userEvent.click(within(halted).getByRole("button", { name: "+$1.00" }));

    await waitFor(() => expect(screen.getByTestId("notice")).toHaveTextContent(vi.haltedBudgetLifted));
    expect(screen.getByTestId("notice")).not.toHaveTextContent(vi.haltedBudget);
    expect(raiseButtons()).toEqual([]);
  });
});

// A notice's raise folds its editor away, and a raise that ends the budget's hold takes
// the notice or its button with it: the keyboard goes where the person carries on.
describe("the keyboard after a raise from a budget notice", () => {
  it("goes to the composer once the over-budget notice's raise lets it write", async () => {
    await haltOnBudget();
    act(() => stream().emit({ type: "run", run: fakeRun({ status: "halted" }) }));
    const over = await screen.findByTestId("over-budget");

    await userEvent.click(within(over).getByRole("button", { name: vi.budgetCard.raise }));
    await userEvent.click(within(over).getByRole("button", { name: "+$1.00" }));
    await waitFor(() => expect(screen.queryByTestId("over-budget")).not.toBeInTheDocument());
    expect(screen.getByRole("textbox")).toHaveFocus();
  });

  it("goes to the composer once the halt's raise lifts the hold", async () => {
    const halted = await haltOnBudget();
    await userEvent.click(within(halted).getByRole("button", { name: vi.budgetCard.raise }));
    await userEvent.click(within(halted).getByRole("button", { name: "+$1.00" }));
    await waitFor(() => expect(raiseButtons()).toEqual([]));
    expect(screen.getByRole("textbox")).toHaveFocus();
  });

  it("stays on a raise when the new cap still holds the budget", async () => {
    const halted = await haltOnBudget();
    await userEvent.click(within(halted).getByRole("button", { name: vi.budgetCard.raise }));
    await userEvent.type(within(halted).getByLabelText(vi.budgetCard.custom), "0.5{Enter}");

    const over = await screen.findByTestId("over-budget");
    const raise = within(over).getByRole("button", { name: vi.budgetCard.raise });
    await waitFor(() => expect(raise).toHaveFocus());
    expect(screen.getByRole("textbox")).toBeDisabled();
    expect(screen.getByTestId("notice")).toHaveTextContent(vi.haltedBudget);
  });
});
