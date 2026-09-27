import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { vi } from "../i18n/vi";
import { toolPending } from "../test/pending";
import { ApprovalBar } from "./approval-bar";
import { ToolArgsDetail } from "./tool-args-detail";
import { ToolCallCard } from "./tool-call-card";

// Long enough that the summary line cuts it, with the part that matters at the end.
const command = `cd /srv/app && ${"echo step && ".repeat(8)}rm -rf ./build/cache`;

describe("ToolArgsDetail", () => {
  it("is closed by default and opens onto the whole command, uncut", async () => {
    render(<ToolArgsDetail args={{ command, timeout: 30 }} />);
    const toggle = screen.getByRole("button", { name: vi.argumentsMore });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByTestId("args-detail")).not.toBeInTheDocument();

    await userEvent.click(toggle);
    const detail = screen.getByTestId("args-detail");
    expect(screen.getByRole("button", { name: vi.argumentsLess })).toHaveAttribute("aria-expanded", "true");
    const block = [...detail.querySelectorAll("pre")].find((pre) => pre.textContent === command);
    expect(block).toBeDefined();
    expect(detail).toHaveTextContent("rm -rf ./build/cache");
    // The rest is still there, as JSON, so nothing the tool received is hidden.
    expect(detail).toHaveTextContent('"timeout": 30');
  });

  it("keeps a file body's line breaks instead of quoting them", async () => {
    render(<ToolArgsDetail args={{ path: "notes.md", content: "dòng một\ndòng hai" }} />);
    await userEvent.click(screen.getByRole("button", { name: vi.argumentsMore }));
    const pres = screen.getByTestId("args-detail").querySelectorAll("pre");
    expect(pres[0].textContent).toBe("dòng một\ndòng hai");
    expect(pres[1].textContent).toBe(JSON.stringify({ path: "notes.md" }, null, 2));
  });

  // An edit is decided on the text it replaces and what replaces it, both as written.
  it("shows an edit's old and new text as written, with the rest as JSON", async () => {
    const args = { path: "notes.md", old: 'dòng một\ndòng "hai"', new: "dòng một", replace_all: false };
    render(<ToolArgsDetail args={args} />);
    await userEvent.click(screen.getByRole("button", { name: vi.argumentsMore }));
    const detail = screen.getByTestId("args-detail");
    const fields = [...detail.querySelectorAll(".args-detail-field")].map((field) => [
      field.querySelector(".args-detail-key")?.textContent,
      field.querySelector("pre")?.textContent,
    ]);
    expect(fields).toEqual([
      ["old", 'dòng một\ndòng "hai"'],
      ["new", "dòng một"],
    ]);
    const pres = detail.querySelectorAll("pre");
    expect(pres[pres.length - 1].textContent).toBe(JSON.stringify({ path: "notes.md", replace_all: false }, null, 2));
  });

  it("reads any argument that spans lines as text, whatever its name", async () => {
    render(<ToolArgsDetail args={{ note: "một\nhai", n: 2 }} />);
    await userEvent.click(screen.getByRole("button", { name: vi.argumentsMore }));
    const pres = screen.getByTestId("args-detail").querySelectorAll("pre");
    expect(pres[0].textContent).toBe("một\nhai");
    expect(pres[1].textContent).toBe(JSON.stringify({ n: 2 }, null, 2));
  });

  it("falls back to pretty JSON for nested arguments", async () => {
    const args = { query: { where: { tag: "sleep" }, limit: 5 }, fields: ["a", "b"] };
    render(<ToolArgsDetail args={args} />);
    await userEvent.click(screen.getByRole("button", { name: vi.argumentsMore }));
    const pres = screen.getByTestId("args-detail").querySelectorAll("pre");
    expect(pres).toHaveLength(1);
    expect(pres[0].textContent).toBe(JSON.stringify(args, null, 2));
  });

  it("offers nothing when the summary line already shows every argument", () => {
    render(<ToolArgsDetail args={{ path: "a.txt", n: 2 }} />);
    expect(screen.queryByRole("button", { name: vi.argumentsMore })).not.toBeInTheDocument();
  });

  it("sits under the approval bar and the tool card, where the summary cuts", async () => {
    render(
      <ApprovalBar
        pending={toolPending({ name: "shell_run", arguments: { command } })}
        busy={false}
        onDecide={() => undefined}
      />,
    );
    render(
      <ToolCallCard
        item={{ kind: "tool", id: "tc", name: "shell_run", arguments: { command }, output: null, status: "running" }}
      />,
    );
    const toggles = screen.getAllByRole("button", { name: vi.argumentsMore });
    expect(toggles).toHaveLength(2);
    await userEvent.click(toggles[0]);
    expect(screen.getByTestId("args-detail")).toHaveTextContent(command);
  });
});
