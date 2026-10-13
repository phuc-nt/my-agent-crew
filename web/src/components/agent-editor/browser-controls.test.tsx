import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi as vitest } from "vitest";
import type { AgentInfo, BrowserConnection } from "../../api/types";
import { vi } from "../../i18n/vi";
import { FakeBackend, fakeAgent } from "../../test/fake-backend";
import { browserMachine } from "../../test/fake-browser";
import { AgentEditor } from "./agent-editor";

const t = vi.editor;
const b = vi.browser;
let backend: FakeBackend;

/** Opens the editor on `agent`, on a machine whose connections say `machine` of its browser. */
function open(agent: AgentInfo, machine?: Partial<BrowserConnection>) {
  backend = new FakeBackend();
  backend.agents = [agent];
  vitest.stubGlobal("fetch", backend.fetch);
  const browser = machine && { ...browserMachine({ enabled: true }), running: [], ...machine };
  render(<AgentEditor agent={agent} agents={[agent]} tools={[]} mcpServers={[]} browser={browser} providers={[]} onBack={() => {}} onChanged={() => {}} />);
}

const reads: AgentInfo = { ...fakeAgent, browser: "read" };
const acts: AgentInfo = { ...fakeAgent, browser: "act", browser_hosts: ["shop.example", "*.bank.example"] };

/** The agent as a server older than the browser reports it: with neither key. */
function older(): AgentInfo {
  const { browser: _mode, browser_hosts: _hosts, ...rest } = fakeAgent;
  return rest;
}

const section = () => within(screen.getByTestId("section-tools"));
const level = () => section().getByRole("combobox", { name: b.mode }) as HTMLSelectElement;
const hosts = () => section().getByRole("textbox", { name: b.hosts }) as HTMLTextAreaElement;
const noHosts = () => expect(section().queryByRole("textbox", { name: b.hosts })).not.toBeInTheDocument();
const warning = () => section().queryByTestId("browser-machine-warning");
const saveButton = () => screen.getByRole("button", { name: t.save });
const save = () => userEvent.click(saveButton());
const saved = () => waitFor(() => expect(screen.getByText(t.clean)).toBeInTheDocument());
const patches = () => backend.requests.filter((r) => r.method === "PATCH").map((r) => r.body);

describe("whether an agent has a browser", () => {
  it("offers the three levels the file takes, under words of their own", () => {
    open(fakeAgent);

    expect(within(level()).getAllByRole("option").map((o) => [(o as HTMLOptionElement).value, o.textContent])).toEqual([
      ["off", "Tắt"],
      ["read", "Đọc"],
      ["act", "Thao tác"],
    ]);
  });

  it("stands with the tools under its own heading, with when a change takes hold", () => {
    open(fakeAgent);

    expect(section().getByRole("heading", { name: b.title })).toBeInTheDocument();
    expect(section().getByText(b.sectionHint)).toBeInTheDocument();
    expect(b.sectionHint).toContain("không cần khởi động lại");
    expect(b.sectionHint).toContain("dừng ngay");
  });

  it("opens on what the file says", () => {
    open(acts);

    expect(level()).toHaveValue("act");
    expect(hosts()).toHaveValue("shop.example\n*.bank.example");
    expect(screen.getByText(t.clean)).toBeInTheDocument();
  });

  it("says one line for the level chosen, as the description of the select", async () => {
    open(fakeAgent);
    expect(level()).toHaveAccessibleDescription(b.modeHint.off);

    await userEvent.selectOptions(level(), "read");
    expect(level()).toHaveAccessibleDescription(b.modeHint.read);
    expect(section().queryByText(b.modeHint.off)).not.toBeInTheDocument();
    // Reading names its five tools, and that opening a page is asked for.
    for (const name of ["browser_navigate", "browser_snapshot", "browser_text", "browser_tabs", "browser_screenshot"])
      expect(b.modeHint.read).toContain(name);
    expect(b.modeHint.read).toContain("phải duyệt");

    await userEvent.selectOptions(level(), "act");
    expect(level()).toHaveAccessibleDescription(b.modeHint.act);
    expect(section().queryByText(b.modeHint.read)).not.toBeInTheDocument();
    expect(b.modeHint.act).toContain("browser_act");
    expect(b.modeHint.act).toContain("luôn hỏi, kể cả khi hội thoại tự chủ");
  });

  it.each(["read", "act"] as const)("saves %s as the one key that changed", async (value) => {
    open(fakeAgent);

    await userEvent.selectOptions(level(), value);
    expect(screen.getByText(t.dirty(1))).toBeInTheDocument();
    await save();

    await saved();
    expect(patches()).toEqual([{ profile: { browser: value } }]);
    // The answer to the save is what the form is rebuilt from.
    expect(level()).toHaveValue(value);
    expect(backend.agents[0].browser).toBe(value);
  });

  it("saves off as the level alone, and leaves the saved hosts in the file", async () => {
    open(acts);

    await userEvent.selectOptions(level(), "off");
    await save();

    await saved();
    expect(patches()).toEqual([{ profile: { browser: "off" } }]);
    expect(backend.agents[0]).toMatchObject({ browser: "off", browser_hosts: ["shop.example", "*.bank.example"] });
  });

  it("has nothing to save once the choice is taken back", async () => {
    open(fakeAgent);

    await userEvent.selectOptions(level(), "act");
    await userEvent.selectOptions(level(), "off");

    expect(screen.getByText(t.clean)).toBeInTheDocument();
  });

  it("cannot be changed on an agent that is not edited here", () => {
    open({ ...acts, editable: false });

    expect(level()).toBeDisabled();
    expect(level()).toHaveValue("act");
    expect(hosts()).toBeDisabled();
    expect(hosts()).toHaveValue("shop.example\n*.bank.example");
  });
});

describe("the hosts an agent's browser opens without asking", () => {
  it("have no box while the agent has no browser, and one at either level", async () => {
    open(fakeAgent);
    noHosts();

    await userEvent.selectOptions(level(), "read");
    expect(hosts()).toHaveValue("");
    await userEvent.selectOptions(level(), "act");
    expect(hosts()).toBeInTheDocument();

    await userEvent.selectOptions(level(), "off");
    noHosts();
  });

  it("are explained by the line under the box, which is its description", () => {
    open(reads);

    expect(hosts()).toHaveAccessibleDescription(b.hostsHint);
    expect(hosts()).not.toHaveAttribute("aria-invalid");
    expect(b.hostsHint).toContain("shop.example");
    expect(b.hostsHint).toContain("*.shop.example");
    expect(b.hostsHint).toContain("Để trống: không giới hạn");
  });

  it("stay in the form as saved when the level goes to off and comes back", async () => {
    open(acts);

    await userEvent.selectOptions(level(), "off");
    noHosts();
    expect(screen.getByText(t.dirty(1))).toBeInTheDocument();
    await userEvent.selectOptions(level(), "act");

    expect(hosts()).toHaveValue("shop.example\n*.bank.example");
    expect(screen.getByText(t.clean)).toBeInTheDocument();
  });

  it("stay in the form as typed, too, across off and back", async () => {
    open(reads);
    await userEvent.type(hosts(), "docs.example");

    await userEvent.selectOptions(level(), "off");
    await userEvent.selectOptions(level(), "read");

    expect(hosts()).toHaveValue("docs.example");
    await save();
    await saved();
    expect(patches()).toEqual([{ profile: { browser_hosts: ["docs.example"] } }]);
  });

  it("are saved as the list alone when only the list changed", async () => {
    open(acts);

    await userEvent.type(hosts(), "{Enter}docs.example");
    expect(screen.getByText(t.dirty(1))).toBeInTheDocument();
    await save();

    await saved();
    expect(patches()).toEqual([{ profile: { browser_hosts: ["shop.example", "*.bank.example", "docs.example"] } }]);
    expect(backend.agents[0].browser_hosts).toEqual(["shop.example", "*.bank.example", "docs.example"]);
  });

  it("are saved with the level when both changed", async () => {
    open(fakeAgent);

    await userEvent.selectOptions(level(), "act");
    await userEvent.type(hosts(), "shop.example{Enter}*.bank.example");
    expect(screen.getByText(t.dirty(2))).toBeInTheDocument();
    await save();

    await saved();
    expect(patches()).toEqual([{ profile: { browser: "act", browser_hosts: ["shop.example", "*.bank.example"] } }]);
  });

  it("are sent as an empty list once the box is emptied", async () => {
    open(acts);

    await userEvent.clear(hosts());
    await save();

    await saved();
    expect(patches()).toEqual([{ profile: { browser_hosts: [] } }]);
    expect(backend.agents[0].browser_hosts).toEqual([]);
    expect(hosts()).toHaveValue("");
  });

  it("are sent small and bare: a capital, the space around a name and a blank line are not part of it", async () => {
    open(reads);

    await userEvent.type(hosts(), "  Shop.Example  {Enter}{Enter}WWW.Bank.example{Enter}");
    // The box keeps what was typed; the list is what it stands for.
    expect(hosts()).toHaveValue("  Shop.Example  \n\nWWW.Bank.example\n");
    expect(section().queryByText(b.hostInvalid("shop.example"))).not.toBeInTheDocument();
    await save();

    await saved();
    expect(patches()).toEqual([{ profile: { browser_hosts: ["shop.example", "www.bank.example"] } }]);
  });

  it("go back to what the file has when the form is reverted", async () => {
    open(acts);
    await userEvent.type(hosts(), "{Enter}docs.example");

    await userEvent.click(screen.getByRole("button", { name: t.revert }));

    expect(hosts()).toHaveValue("shop.example\n*.bank.example");
    expect(screen.getByText(t.clean)).toBeInTheDocument();
  });
});

describe("a host line the server would refuse", () => {
  const PASTED = "https://shop.example/cart";

  it("is named under the box, in what to take off it, and holds the save", async () => {
    open(reads);

    await userEvent.type(hosts(), `docs.example{Enter}${PASTED}`);

    const said = "«https://shop.example/cart» không phải tên máy chủ: bỏ https://, cổng và đường dẫn.";
    expect(section().getByText(said)).toHaveClass("field-error");
    expect(hosts()).toHaveAttribute("aria-invalid", "true");
    expect(hosts()).toHaveAccessibleDescription(`${b.hostsHint} ${said}`);
    expect(saveButton()).toBeDisabled();
    expect(screen.getByTestId("save-held")).toBeInTheDocument();
    expect(patches()).toEqual([]);
  });

  it.each([
    ["a port", "shop.example:8443"],
    ["a path", "shop.example/cart"],
    ["a star in the wrong place", "shop.*.example"],
  ])("is refused for %s", async (_what, line) => {
    open(reads);

    await userEvent.type(hosts(), line);

    expect(section().getByText(b.hostInvalid(line))).toBeInTheDocument();
    expect(saveButton()).toBeDisabled();
  });

  it("lets the save through once the line is a host name", async () => {
    open(reads);
    await userEvent.type(hosts(), PASTED);
    expect(saveButton()).toBeDisabled();

    await userEvent.clear(hosts());
    await userEvent.type(hosts(), "shop.example");

    expect(section().queryByText(b.hostInvalid(PASTED))).not.toBeInTheDocument();
    expect(hosts()).not.toHaveAttribute("aria-invalid");
    expect(screen.queryByTestId("save-held")).not.toBeInTheDocument();
    await save();
    await saved();
    expect(patches()).toEqual([{ profile: { browser_hosts: ["shop.example"] } }]);
  });

  it("keeps its box on screen when the level goes to off, so there is somewhere to fix it", async () => {
    open(reads);
    await userEvent.type(hosts(), PASTED);

    await userEvent.selectOptions(level(), "off");

    expect(hosts()).toHaveValue(PASTED);
    expect(section().getByText(b.hostInvalid(PASTED))).toBeInTheDocument();
    expect(saveButton()).toBeDisabled();

    // Emptied, the list is as the file has it: nothing is wrong, and off has no box.
    await userEvent.clear(hosts());
    noHosts();
    expect(saveButton()).toBeEnabled();
  });

  it("does not hold a save of something else for a line the file already had", async () => {
    // A file edited by hand: the form would not have let this line through, and would have
    // written it small. The box shows it as the file has it and the editor still draws.
    open({ ...reads, browser_hosts: ["Shop.Example", "https://pay.example"] });
    expect(hosts()).toHaveValue("Shop.Example\nhttps://pay.example");
    expect(screen.getByText(t.clean)).toBeInTheDocument();
    expect(hosts()).not.toHaveAttribute("aria-invalid");

    await userEvent.selectOptions(level(), "act");
    await save();

    await saved();
    expect(patches()).toEqual([{ profile: { browser: "act" } }]);
    expect(hosts()).toHaveValue("Shop.Example\nhttps://pay.example");
  });

  it("is named once the list the file had is touched", async () => {
    open({ ...reads, browser_hosts: ["https://pay.example"] });

    await userEvent.type(hosts(), "{Enter}shop.example");

    expect(section().getByText(b.hostInvalid("https://pay.example"))).toBeInTheDocument();
    expect(saveButton()).toBeDisabled();
  });
});

describe("a level chosen on a machine that cannot give a browser", () => {
  it("is told the machine has the browser switched off", async () => {
    open(reads, { enabled: false });

    expect(warning()).toHaveTextContent(b.machineOffForAgent);
    expect(warning()).toHaveClass("warn-text");
    expect(b.machineOffForAgent).toContain("browser_enabled");
    expect(level()).toHaveAccessibleDescription(`${b.modeHint.read} ${b.machineOffForAgent}`);
  });

  it("is told the machine has no browser installed", () => {
    open(acts, { enabled: true, installed: false, missing: "browser" });

    expect(warning()).toHaveTextContent(b.machineMissingForAgent);
    expect(level()).toHaveAccessibleDescription(`${b.modeHint.act} ${b.machineMissingForAgent}`);
  });

  it("is told of the switch first, on a machine that has both against it", () => {
    open(reads, { enabled: false, installed: false, missing: "playwright" });

    expect(warning()).toHaveTextContent(b.machineOffForAgent);
    expect(warning()).not.toHaveTextContent(b.machineMissingForAgent);
  });

  it("is told as soon as it is chosen, before any save, and no longer once taken back", async () => {
    open(fakeAgent, { enabled: false });
    expect(warning()).not.toBeInTheDocument();

    await userEvent.selectOptions(level(), "read");
    expect(warning()).toHaveTextContent(b.machineOffForAgent);

    await userEvent.selectOptions(level(), "off");
    expect(warning()).not.toBeInTheDocument();
    expect(level()).toHaveAccessibleDescription(b.modeHint.off);
  });

  it("is told nothing on a machine that has a browser to start", () => {
    open(acts, { enabled: true, installed: true });

    expect(warning()).not.toBeInTheDocument();
    expect(level()).toHaveAccessibleDescription(b.modeHint.act);
  });

  it("is told nothing while the page has not read the machine yet", () => {
    open(acts);

    expect(warning()).not.toBeInTheDocument();
  });
});

describe("the browser's tools and the agent's tool list", () => {
  it("are said, under the list, to come with the browser setting and not with a tick", () => {
    open(fakeAgent);

    expect(section().getByText(b.outsideList)).toBeInTheDocument();
    expect(b.outsideList).toContain("browser_*");
  });
});

describe("the editor of an agent on a server that knows no browser", () => {
  it("has no browser setting, no host box and no word about the browser's tools", async () => {
    const agent = older();
    expect(agent).not.toHaveProperty("browser");
    expect(agent).not.toHaveProperty("browser_hosts");
    open(agent, { enabled: false });
    backend.browser.old = true;

    expect(section().queryByRole("combobox", { name: b.mode })).not.toBeInTheDocument();
    noHosts();
    expect(section().queryByRole("heading", { name: b.title })).not.toBeInTheDocument();
    expect(section().queryByText(b.sectionHint)).not.toBeInTheDocument();
    expect(section().queryByText(b.outsideList)).not.toBeInTheDocument();
    expect(warning()).not.toBeInTheDocument();
    // The rest of the section is as it was.
    expect(section().getByRole("combobox", { name: t.scriptCalls })).toHaveValue("read_only");
    expect(screen.getByText(t.clean)).toBeInTheDocument();
  });

  it("sends neither key with a save of something else", async () => {
    open(older());
    backend.browser.old = true;

    await userEvent.selectOptions(section().getByRole("combobox", { name: t.scriptCalls }), "gated");
    await save();

    await saved();
    expect(patches()).toEqual([{ profile: { script_calls: "gated" } }]);
  });
});
