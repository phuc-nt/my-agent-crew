import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { useAgentDraft } from "../../hooks/use-agent-draft";
import { vi } from "../../i18n/vi";
import { agent, CHATS, CREW, LEADS, open, radio, rows, saved, section, ticked } from "../../test/tool-picker-screen";
import { ToolsSection } from "./tools-section";

const t = vi.editor;

// The rows are the server's judgement of the agent as it is saved. What the form holds and
// has not saved yet, the server has not judged.
describe("a change to the mode or to the delegates that is not saved yet", () => {
  const hands = () => within(screen.getByTestId("delegate-picker")).getByRole("checkbox", { name: /Dev/ });
  const mode = () => screen.getByRole("combobox", { name: t.mode });
  const hint = () => section().queryByText(t.toolsFollowSaved);

  it("is to be saved first, the picker says in a line under it, and its rows stay as saved", async () => {
    expect(t.toolsFollowSaved).toContain(`“${t.mode}”`);
    expect(t.toolsFollowSaved).toContain(`“${t.delegates}”`);
    open(agent({ listed: ["write_file"] }));
    // A change to any other field moves no row, and says nothing here.
    await userEvent.type(screen.getByLabelText(t.name), " mới");
    expect(hint()).not.toBeInTheDocument();
    expect(radio(t.toolsPick)).not.toHaveAccessibleDescription();

    await userEvent.click(hands());
    expect(section().getByTestId("tool-picker").nextElementSibling).toBe(hint());
    expect(radio(t.toolsPick)).toHaveAccessibleDescription(t.toolsFollowSaved);
    expect(rows()).toEqual(CHATS);
    await userEvent.click(hands());
    expect(hint()).not.toBeInTheDocument();

    await userEvent.selectOptions(mode(), "work");
    expect(hint()).toBeInTheDocument();
    expect(rows()).toEqual(CHATS);
  });

  // The answer to the save carries the names for the agent it made: no second read is needed.
  it.each([
    ["a delegate", () => userEvent.click(hands())],
    ["the mode", () => userEvent.selectOptions(mode(), "work")],
  ])("gives way to the rows of the agent the save made, once the save of %s lands", async (_what, change) => {
    open(agent({ listed: ["write_file"] }));
    await change();
    await saved();

    expect(hint()).not.toBeInTheDocument();
    expect(rows()).toEqual(LEADS);
    expect(ticked()).toEqual(["write_file"]);
  });
});

describe("an agent that is not saved yet", () => {
  /** The list the form holds, which is what a save of it would write. */
  let held: string[] | null | undefined;
  function Blank() {
    const form = useAgentDraft(null);
    held = form.draft.tools;
    return <ToolsSection form={form} readOnly={false} tools={CREW} mcpServers={[]} />;
  }

  // No server has judged it yet: the catalogue's own marks say what no list gives.
  it("is offered every tool the catalogue does not mark, and starts from them all", async () => {
    render(<Blank />);
    expect(rows()).toEqual(["ask_user", "delegate", "web_search", "write_file"]);
    await userEvent.click(radio(t.toolsPick));

    expect(ticked()).toEqual(["ask_user", "delegate", "web_search", "write_file"]);
    // And no name beside them, which no row would show.
    expect(held).toEqual(["ask_user", "delegate", "web_search", "write_file"]);
    expect(section().queryByText(t.toolsFollowSaved)).not.toBeInTheDocument();
  });
});
