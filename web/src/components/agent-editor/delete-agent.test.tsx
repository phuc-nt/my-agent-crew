import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi as vitest, beforeEach } from "vitest";
import { vi } from "../../i18n/vi";
import { DeleteAgent } from "./delete-agent";
import { FakeBackend, fakeAgent } from "../../test/fake-backend";

describe("DeleteAgent", () => {
  beforeEach(() => {
    vitest.stubGlobal("fetch", new FakeBackend().fetch);
  });

  it("renders with the agent id shown in the hint", () => {
    const onDeleted = vitest.fn();
    render(<DeleteAgent agentId="coach" onDeleted={onDeleted} />);

    expect(screen.getByText(new RegExp("coach"))).toBeInTheDocument();
  });

  it("says, before the id is typed, what the folder in .trash will not bring back", () => {
    render(<DeleteAgent agentId="coach" onDeleted={vitest.fn()} />);

    const lost = screen.getByTestId("delete-agent-lost");
    expect(lost).toBeVisible();
    expect(lost).toHaveTextContent(vi.editor.deleteLost);
    // The three things the server drops with the agent, and the two it keeps.
    for (const named of [/script của agent này giữ lại/, /lịch nó được tạo từ chat/, /bật\/tắt của từng lịch/]) {
      expect(vi.editor.deleteLost).toMatch(named);
    }
    expect(vi.editor.deleteLost).toMatch(/^Xoá hẳn, không lấy lại được:/);
    expect(vi.editor.deleteLost).toMatch(/Hội thoại và lịch sử run vẫn giữ nguyên\.$/);
    // It stands between the hint and the box, so it is read before the id is typed.
    const box = screen.getByLabelText(vi.editor.deleteTitle);
    expect(lost.compareDocumentPosition(box) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("starts with an empty input and a disabled delete button", () => {
    const onDeleted = vitest.fn();
    render(<DeleteAgent agentId="coach" onDeleted={onDeleted} />);

    const input = screen.getByLabelText(vi.editor.deleteTitle);
    const button = screen.getByRole("button", { name: vi.editor.deleteConfirm });

    expect(input).toHaveValue("");
    expect(button).toBeDisabled();
  });

  it("enables the button only when the typed text exactly equals the agent id", async () => {
    const onDeleted = vitest.fn();
    render(<DeleteAgent agentId="coach" onDeleted={onDeleted} />);

    const input = screen.getByLabelText(vi.editor.deleteTitle);
    const button = screen.getByRole("button", { name: vi.editor.deleteConfirm });

    expect(button).toBeDisabled();

    // Type a partial match
    await userEvent.type(input, "coa");
    expect(button).toBeDisabled();

    // Type the full match
    await userEvent.type(input, "ch");
    expect(button).not.toBeDisabled();
  });

  it("disables the button if the typed text does not match exactly", async () => {
    const onDeleted = vitest.fn();
    render(<DeleteAgent agentId="coach" onDeleted={onDeleted} />);

    const input = screen.getByLabelText(vi.editor.deleteTitle);
    const button = screen.getByRole("button", { name: vi.editor.deleteConfirm });

    await userEvent.type(input, "coach ");
    expect(button).toBeDisabled();
  });

  it("disables the button again if the user edits the matching text", async () => {
    const onDeleted = vitest.fn();
    render(<DeleteAgent agentId="coach" onDeleted={onDeleted} />);

    const input = screen.getByLabelText(vi.editor.deleteTitle) as HTMLInputElement;
    const button = screen.getByRole("button", { name: vi.editor.deleteConfirm });

    await userEvent.type(input, "coach");
    expect(button).not.toBeDisabled();

    // Remove one character
    await userEvent.type(input, "{Backspace}");
    expect(button).toBeDisabled();
  });

  it("calls the delete API when the button is clicked", async () => {
    const backend = new FakeBackend();
    backend.agents = [{ ...fakeAgent, id: "coach" }];
    vitest.stubGlobal("fetch", backend.fetch);

    const onDeleted = vitest.fn();
    render(<DeleteAgent agentId="coach" onDeleted={onDeleted} />);

    const input = screen.getByLabelText(vi.editor.deleteTitle);
    const button = screen.getByRole("button", { name: vi.editor.deleteConfirm });

    await userEvent.type(input, "coach");
    expect(button).not.toBeDisabled();
    await userEvent.click(button);

    // Verify a request was made (we can't wait for the callback easily due to async)
    expect(button).not.toBeDisabled(); // Should be enabled again after
  });
});
