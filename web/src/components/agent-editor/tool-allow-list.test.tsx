import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { vi } from "../../i18n/vi";
import { agent, box, CHATS, CREW, HANDED, LEADS, open, radio, rows, saved, type Shown, tick, ticked } from "../../test/tool-picker-screen";

const t = vi.editor;

describe("the rows the picker offers", () => {
  it("are the names the server lists for this agent, not what the rest of the crew holds", () => {
    open(agent());
    expect(rows()).toEqual(CHATS);
    // Described by the catalogue where it has a row for the name, and bare where it has none.
    expect(box("web_search").closest("li")).toHaveTextContent("Công cụ web_search");
    expect(box("memory_save").closest("li")).toHaveTextContent(/^memory_save$/);
  });

  // Who hands work out is the server's to say: nothing else in the profile is read for it.
  it.each([
    ["is offered to a plain agent the server lists it for", agent({ listable_tools: LEADS }), LEADS],
    ["is not offered to a master the server does not list it for", agent({ id: "default", is_master: true, mode: "work", delegates: ["dev"] }), CHATS],
  ])("`delegate` %s", (_what, shown, offered) => {
    open(shown);
    expect(rows()).toEqual(offered);
  });

  // The catalogue lists what some agent holds: with this list saved, nobody holds the tool.
  it("keep `delegate` when no agent holds it any more, in words of its own, to be ticked back", async () => {
    open(agent({ listable_tools: LEADS, listed: ["write_file"], tools: ["write_file"] }), CREW.filter((row) => row.name !== "delegate"));
    expect(rows()).toEqual(LEADS);
    expect(box("delegate").closest("li")).toHaveTextContent(t.toolDelegate);
    await tick("delegate");
    expect(await saved()).toEqual([{ tools: ["write_file", "delegate"] }]);
  });
});

describe("the chosen list, when it is switched on", () => {
  it("starts from what this agent holds among those names, in the rows' order", async () => {
    open(agent());
    await userEvent.click(radio(t.toolsPick));
    expect(ticked()).toEqual(["web_search", "write_file"]);
    expect(await saved()).toEqual([{ tools: ["web_search", "write_file"] }]);
  });

  // Left out, the list would take from the agent the one thing that makes it a lead.
  it("starts with `delegate` for an agent that holds it, under the catalogue's words for it", async () => {
    open(agent({ listable_tools: LEADS, tools: ["write_file", "delegate", ...HANDED] }));
    await userEvent.click(radio(t.toolsPick));
    expect(box("delegate").closest("li")).toHaveTextContent("Công cụ delegate");
    expect(ticked()).toEqual(["delegate", "write_file"]);
    expect(await saved()).toEqual([{ tools: ["delegate", "write_file"] }]);
  });

  it("starts from every row when the agent holds none of them", async () => {
    open(agent({ tools: HANDED }));
    await userEvent.click(radio(t.toolsPick));
    expect(ticked()).toEqual(CHATS);
  });

  it("goes back to the list the file has, as it is written, after a detour through every tool", async () => {
    open(agent({ listed: ["write_file", "tool_script", "memory_save"], tools: ["write_file"] }));
    await userEvent.click(radio(t.toolsAll));
    expect(screen.getByText(t.dirty(1))).toBeInTheDocument();
    expect(rows()).toEqual(CHATS);
    await userEvent.click(radio(t.toolsPick));
    expect(ticked()).toEqual(["memory_save", "write_file", "tool_script"]);
    expect(screen.getByText(t.clean)).toBeInTheDocument();
  });
});

describe("a name the list holds that the server does not list for this agent", () => {
  // `delegate` on an agent that hands no work out, a handed tool, a tool of a server the
  // crew no longer has, and a tool the machine cannot run today.
  const NOTHING_FROM = ["delegate", "tool_script", "mcp__gone__fetch", "image_read"];
  const old = (rest: Shown = {}) => agent({ listed: ["web_search", ...NOTHING_FROM], ...rest });

  it("opens ticked in a row of its own after the others, said to bring nothing, with nothing to save", () => {
    open(old());
    expect(radio(t.toolsPick)).toBeChecked();
    expect(rows()).toEqual([...CHATS, ...NOTHING_FROM]);
    expect(ticked()).toEqual(["web_search", ...NOTHING_FROM]);
    for (const name of NOTHING_FROM) expect(box(name)).toHaveAccessibleDescription(t.toolNotGiven);
    expect(box("web_search")).not.toHaveAccessibleDescription();
    expect(screen.getByRole("button", { name: t.save })).toBeDisabled();
  });

  it("stays in the list when another row is ticked: only the person takes a name off", async () => {
    open(old());
    await tick("write_file");
    expect(await saved()).toEqual([{ tools: ["web_search", ...NOTHING_FROM, "write_file"] }]);
    expect(ticked()).toEqual(["web_search", "write_file", ...NOTHING_FROM]);
  });

  it("leaves the list once it is unticked, and its row goes with it", async () => {
    open(old());
    await tick("tool_script");
    expect(rows()).toEqual([...CHATS, "delegate", "mcp__gone__fetch", "image_read"]);
    expect(await saved()).toEqual([{ tools: ["web_search", "delegate", "mcp__gone__fetch", "image_read"] }]);
  });

  // The row is gone under the keyboard that unticked it, which is then on no row at all.
  it.each([
    ["the row that took its place", "tool_script", "mcp__gone__fetch"],
    ["the last row, when it stood last itself", "image_read", "mcp__gone__fetch"],
  ])("hands the keyboard to %s once it is unticked", async (_what, name, next) => {
    open(old());
    await tick(name);
    await waitFor(() => expect(box(next)).toHaveFocus());
  });

  it("hands the keyboard to “every tool” when it was the last name, which is what the form then says", async () => {
    open(agent({ listed: ["tool_script"] }));
    await tick("tool_script");
    await waitFor(() => expect(radio(t.toolsAll)).toHaveFocus());
    expect(radio(t.toolsAll)).toBeChecked();
  });

  // A tap unticks without taking the keyboard: it stays in the field the person is typing in.
  it("leaves the keyboard where it is when it was not on the row", () => {
    open(old());
    screen.getByLabelText(t.name).focus();
    fireEvent.click(box("tool_script"));
    expect(rows()).not.toContain("tool_script");
    expect(screen.getByLabelText(t.name)).toHaveFocus();
  });

  it("has one row when the list holds it twice, and both go with it", async () => {
    open(agent({ listed: ["tool_script", "web_search", "tool_script"] }));
    expect(rows()).toEqual([...CHATS, "tool_script"]);
    await tick("tool_script");
    expect(await saved()).toEqual([{ tools: ["web_search"] }]);
  });

  it("cannot be unticked on an agent that is not edited here", () => {
    open(old({ editable: false }));
    expect(box("tool_script")).toBeChecked();
    expect(box("tool_script")).toBeDisabled();
  });

  // The list is rewritten only by a change to the list: a hand-written file keeps its own.
  it("sends no list at all when another field is what was changed", async () => {
    const backend = open(old());
    await userEvent.type(screen.getByLabelText(t.name), " mới");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: t.scriptCalls }), "gated");

    const [sent] = await saved();
    expect(sent).toEqual({ name: "Agent mới", script_calls: "gated" });
    expect(sent).not.toHaveProperty("tools");
    expect(backend.agents[0].declared.tools).toEqual(["web_search", ...NOTHING_FROM]);
  });

  it("is not `delegate` on an agent the server lists it for: a row like any other", async () => {
    open(agent({ listable_tools: LEADS, listed: ["web_search", "delegate", "tool_script"] }));
    expect(rows()).toEqual([...LEADS, "tool_script"]);
    expect(box("delegate")).not.toHaveAccessibleDescription();
    await tick("write_file");
    expect(await saved()).toEqual([{ tools: ["web_search", "delegate", "tool_script", "write_file"] }]);
  });

  // The server reads any list as a cap, so the form does too: a list still, not "all".
  it("makes a list by itself, and the next tick is written after it", async () => {
    open(agent({ listed: ["delegate", "tool_script"] }));
    expect(radio(t.toolsPick)).toBeChecked();
    expect(ticked()).toEqual(["delegate", "tool_script"]);
    await tick("web_search");
    expect(await saved()).toEqual([{ tools: ["delegate", "tool_script", "web_search"] }]);
  });
});
