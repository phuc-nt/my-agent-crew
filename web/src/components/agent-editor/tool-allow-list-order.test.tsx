// A list is written in an order: the file's own. A tick only says whether a name is in it,
// so a name ticked again goes back to where the file has it, and the form has nothing to
// save. A name the file's list never held is written after the file's names, where the
// rows show it.
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { vi } from "../../i18n/vi";
import { agent, LEADS, open, radio, rows, saved, tick, ticked } from "../../test/tool-picker-screen";

const t = vi.editor;
/** The file's list, in an order of its own: the rows stand in another. */
const FILE = ["write_file", "memory_save", "web_search"];

const nothingToSave = () => {
  expect(screen.getByText(t.clean)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: t.save })).toBeDisabled();
};

describe("a row unticked and ticked again", () => {
  it.each(FILE)("leaves nothing to save: %s is back where the file's list has it", async (name) => {
    open(agent({ listed: FILE }));
    expect(rows()).not.toEqual(FILE);

    await tick(name);
    expect(screen.getByText(t.dirty(1))).toBeInTheDocument();
    await tick(name);

    nothingToSave();
  });

  it("leaves nothing to save when every row went and came back in another order", async () => {
    open(agent({ listed: FILE }));

    for (const name of ["memory_save", "write_file"]) await tick(name);
    for (const name of ["memory_save", "write_file"]) await tick(name);

    nothingToSave();
  });

  it("leaves nothing to save around a name the server does not list, which keeps its place", async () => {
    open(agent({ listed: ["write_file", "tool_script", "web_search"] }));

    await tick("write_file");
    await tick("write_file");

    nothingToSave();
  });

  it("puts a name the file writes twice back in both its places", async () => {
    open(agent({ listed: ["write_file", "web_search", "write_file"] }));

    await tick("write_file");
    expect(ticked()).toEqual(["web_search"]);
    await tick("write_file");

    nothingToSave();
  });
});

describe("a name ticked that the file's list never held", () => {
  it("is written after the file's names, which keep their order", async () => {
    open(agent({ listed: ["write_file", "memory_save"] }));

    await tick("web_search");

    expect(await saved()).toEqual([{ tools: ["write_file", "memory_save", "web_search"] }]);
  });

  it("stays after them when one of the file's names is ticked back later", async () => {
    open(agent({ listed: ["write_file", "memory_save"] }));

    await tick("write_file");
    await tick("web_search");
    await tick("write_file");

    expect(await saved()).toEqual([{ tools: ["write_file", "memory_save", "web_search"] }]);
  });

  it("is written among the other new names as the rows stand, whichever was ticked first", async () => {
    open(agent({ listable_tools: LEADS, listed: ["write_file"] }));

    await tick("web_search");
    await tick("delegate");

    expect(await saved()).toEqual([{ tools: ["write_file", "delegate", "web_search"] }]);
  });

  // The file lists none: every name of a list switched on here is new to it.
  it("is written as the rows stand in a list switched on in this session, a tick taken back or not", async () => {
    open(agent());
    await userEvent.click(radio(t.toolsPick));
    expect(ticked()).toEqual(["web_search", "write_file"]);

    await tick("web_search");
    await tick("memory_save");
    await tick("web_search");

    expect(await saved()).toEqual([{ tools: ["memory_save", "web_search", "write_file"] }]);
  });
});
