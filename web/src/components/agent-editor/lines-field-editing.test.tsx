// What a list-of-strings field does while someone is typing in it.
//
// These render it the way the editor does — inside a parent that holds the list and
// feeds it back — because the defects only appear on the round trip. A test that passes
// a fixed `value` never re-renders the field with a filtered list, so it cannot see the
// blank line disappear from under the cursor.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { LinesField } from "./fields";

function Editing({ initial }: { initial: string[] }) {
  const [lines, setLines] = useState(initial);
  return (
    <>
      <LinesField label="Mẫu lệnh hỏi" value={lines} onChange={setLines} />
      <output data-testid="lines">{JSON.stringify(lines)}</output>
    </>
  );
}

describe("LinesField while it is being edited", () => {
  it("keeps the blank line opened between two entries", async () => {
    render(<Editing initial={["a", "b"]} />);
    const box = screen.getByLabelText("Mẫu lệnh hỏi");

    // Enter pressed at the end of the first line, which is how a new entry gets added
    // in the middle of an ask-list. The empty line is not an entry, so the parent's list
    // does not change — and the field must not treat that as a reason to reset itself.
    await userEvent.click(box);
    // Straight to the end of the first line. jsdom lays out no text, so {End} would run
    // to the end of the whole box rather than the end of the row the cursor is on.
    (box as HTMLTextAreaElement).setSelectionRange(1, 1);
    await userEvent.keyboard("{Enter}x");

    expect(box).toHaveValue("a\nx\nb");
    expect(screen.getByTestId("lines")).toHaveTextContent('["a","x","b"]');
  });

  it("keeps the blank line opened at the end of the list", async () => {
    render(<Editing initial={["a"]} />);
    const box = screen.getByLabelText("Mẫu lệnh hỏi");

    await userEvent.click(box);
    await userEvent.keyboard("{End}{Enter}");

    expect(box).toHaveValue("a\n");
    expect(screen.getByTestId("lines")).toHaveTextContent('["a"]');
  });

  it("takes the new list when it changes from outside, discarding the buffer", async () => {
    function Reverting() {
      const [lines, setLines] = useState<string[]>(["a"]);
      return (
        <>
          <LinesField label="Mẫu lệnh hỏi" value={lines} onChange={setLines} />
          <button type="button" onClick={() => setLines(["rm -rf"])}>
            hoàn tác
          </button>
        </>
      );
    }
    render(<Reverting />);
    const box = screen.getByLabelText("Mẫu lệnh hỏi");
    await userEvent.click(box);
    await userEvent.keyboard("{End}{Enter}");

    // A revert or a save replaces the list; the half-typed line goes with it rather than
    // surviving on top of a profile the person asked to restore.
    await userEvent.click(screen.getByRole("button", { name: "hoàn tác" }));

    expect(box).toHaveValue("rm -rf");
  });
});
