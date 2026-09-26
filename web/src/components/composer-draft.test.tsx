import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { memoryStorage } from "../test/memory-storage";
import { Composer } from "./composer";

let store: Map<string, string>;

beforeEach(() => {
  store = memoryStorage();
});

afterEach(() => vitest.unstubAllGlobals());

function composer(draftKey: string, extra: { draft?: string; onSend?: (text: string) => void } = {}) {
  return (
    <Composer
      disabled={false}
      busy={false}
      draftKey={draftKey}
      draft={extra.draft}
      onSend={extra.onSend ?? (() => undefined)}
      onStop={() => undefined}
    />
  );
}

describe("the composer's draft per conversation", () => {
  it("puts the half-written text back after a switch away and back", async () => {
    const view = render(composer("c1"));
    await userEvent.type(screen.getByRole("textbox"), "Hôm nay ăn");

    view.rerender(composer("c2"));
    expect(screen.getByRole("textbox")).toHaveValue("");

    view.rerender(composer("c1"));
    expect(screen.getByRole("textbox")).toHaveValue("Hôm nay ăn");
  });

  it("clears the kept draft once the message is sent", async () => {
    const onSend = vitest.fn();
    const view = render(composer("c1", { onSend }));
    await userEvent.type(screen.getByRole("textbox"), "gửi đi{Enter}");
    expect(onSend).toHaveBeenCalledWith("gửi đi");
    expect(store.size).toBe(0);

    view.rerender(composer("c2", { onSend }));
    view.rerender(composer("c1", { onSend }));
    expect(screen.getByRole("textbox")).toHaveValue("");
  });

  it("does not carry a suggestion picked in one conversation into the next one's draft", async () => {
    const view = render(composer("c1"));
    await userEvent.type(screen.getByRole("textbox"), "của c1");
    view.rerender(composer("c2", { draft: "gợi ý" }));
    expect(screen.getByRole("textbox")).toHaveValue("gợi ý");

    view.rerender(composer("c1", { draft: "gợi ý" }));
    expect(screen.getByRole("textbox")).toHaveValue("của c1");
  });
});
