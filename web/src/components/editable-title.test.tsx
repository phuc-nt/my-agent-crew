import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../i18n/vi";
import { EditableTitle } from "./editable-title";

const OLD = "Tên cũ";

function mount(title = OLD) {
  const onRename = vitest.fn();
  render(<EditableTitle title={title} onRename={onRename} />);
  const field = () => screen.getByRole<HTMLInputElement>("textbox", { name: vi.rename });
  const open = () => userEvent.click(screen.getByRole("button", { name: title || vi.newConversation }));
  /** Opens the editor and types over the name, the way a person finds it selected. */
  const edit = async (keys: string) => {
    await open();
    await userEvent.keyboard(keys);
  };
  return { onRename, field, open, edit };
}

describe("renaming a conversation where it is shown", () => {
  it("keeps the new name on Enter", async () => {
    const { onRename, edit } = mount();
    await edit("Tên mới{Enter}");
    expect(onRename).toHaveBeenCalledWith("Tên mới");
  });

  it("puts the old name back on Escape without saving", async () => {
    const { onRename, edit } = mount();
    await edit("Tên nháp{Escape}");
    expect(onRename).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(OLD);
  });

  // Someone who typed a name and clicked elsewhere meant the name.
  it("keeps the new name when the field loses focus", async () => {
    const { onRename, edit } = mount();
    await edit("Tên mới");
    await userEvent.tab();
    expect(onRename).toHaveBeenCalledWith("Tên mới");
  });

  it("opens from the keyboard, so the title is not a mouse-only control", async () => {
    const { field } = mount();
    await userEvent.tab();
    await userEvent.keyboard("{Enter}");
    expect(field()).toBeInTheDocument();
  });

  // The name arrives selected: typing replaces it rather than appending to it.
  it("offers the old name ready to be typed over", async () => {
    const { open, field } = mount();
    await open();
    expect(field()).toHaveValue(OLD);
    expect(field().selectionStart).toBe(0);
    expect(field().selectionEnd).toBe(OLD.length);
  });

  // A control that opens an editor must not cost the page its heading.
  it("stays a level-1 heading while it is being edited", async () => {
    const { open } = mount();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(OLD);
    await open();
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
  });

  it("saves nothing when the name is blanked or left unchanged", async () => {
    const { onRename, edit } = mount();
    await edit("   {Enter}");
    expect(onRename).not.toHaveBeenCalled();

    await edit(`${OLD}{Enter}`);
    expect(onRename).not.toHaveBeenCalled();
  });

  it("shows the placeholder name for a conversation with none", () => {
    render(<EditableTitle title="" onRename={vitest.fn()} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(vi.newConversation);
    expect(screen.getByRole("button", { name: vi.newConversation })).toBeInTheDocument();
  });
});

describe("renaming a canvas beside the conversation", () => {
  const canvasTitle = (props: { title?: string; startEditing?: boolean } = {}) => {
    const onRename = vitest.fn();
    render(
      <EditableTitle
        title={props.title ?? "Ghi chú"}
        onRename={onRename}
        level={2}
        maxLength={200}
        label={vi.canvas.rename}
        hint={vi.canvas.renameHint}
        placeholder={vi.canvas.untitled}
        startEditing={props.startEditing}
      />,
    );
    return { onRename, field: () => screen.getByRole<HTMLInputElement>("textbox", { name: vi.canvas.rename }) };
  };

  it("names its part of the page under the conversation's heading, with its own field and placeholder", async () => {
    canvasTitle({ title: "" });
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent(vi.canvas.untitled);
    expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
    expect(screen.getByRole("button", { name: vi.canvas.untitled })).toHaveAttribute("title", vi.canvas.renameHint);

    await userEvent.click(screen.getByRole("button", { name: vi.canvas.untitled }));
    expect(screen.getByRole("textbox", { name: vi.canvas.rename })).toHaveAttribute("maxLength", "200");
  });

  it("opens ready to type over the name of something just made", async () => {
    const { onRename, field } = canvasTitle({ title: vi.canvas.untitled, startEditing: true });

    await waitFor(() => expect(field()).toHaveFocus());
    expect(field().selectionStart).toBe(0);
    expect(field().selectionEnd).toBe(vi.canvas.untitled.length);

    await userEvent.keyboard("Kế hoạch{Enter}");
    expect(onRename).toHaveBeenCalledWith("Kế hoạch");
  });
});
