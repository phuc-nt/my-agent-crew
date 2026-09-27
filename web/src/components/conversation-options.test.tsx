import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../i18n/vi";
import { FakeBackend, listItem, storedMessage } from "../test/fake-backend";
import { ConversationOptions } from "./conversation-options";

let backend: FakeBackend;
let saved: { name: string; blob: Blob } | null;

beforeEach(() => {
  backend = new FakeBackend();
  vitest.stubGlobal("fetch", backend.fetch);
  saved = null;
  // jsdom has no object URLs and does not download; record what would have been saved.
  let blob: Blob | null = null;
  URL.createObjectURL = (value: Blob | MediaSource) => {
    blob = value as Blob;
    return "blob:export";
  };
  URL.revokeObjectURL = () => {};
  vitest.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    if (blob) saved = { name: this.download, blob };
  });
});

afterEach(() => {
  vitest.unstubAllGlobals();
  vitest.restoreAllMocks();
});

function options(conversationId: string) {
  const detail = backend.conversations.get(conversationId)!;
  render(
    <ConversationOptions
      conversation={listItem(detail)}
      agentName="Coach"
      skills={[]}
      onToggleAutonomous={() => {}}
      onToggleSkill={() => {}}
      onRevokeAutoApprove={() => {}}
    />,
  );
  fireEvent.click(screen.getByTestId("conversation-options"));
}

describe("exporting a conversation as markdown", () => {
  it("downloads '<title>.md' built from the stored messages", async () => {
    const c = backend.create({
      title: "Kế hoạch ngủ",
      messages: [storedMessage("user", "chào", { created_at: "2026-09-25T01:00:00Z" })],
    });
    options(c.id);

    fireEvent.click(screen.getByRole("button", { name: vi.options.exportMarkdown }));

    await waitFor(() => expect(saved).not.toBeNull());
    expect(saved!.name).toBe("Kế hoạch ngủ.md");
    expect(await saved!.blob.text()).toBe("# Kế hoạch ngủ\n\n## Bạn · 25/09/2026 08:00 (UTC+7)\n\nchào\n");
  });

  // A tooltip never shows on a phone, where the owner exports most.
  it("says in plain view that the file's times follow this device's time zone", () => {
    const c = backend.create({ title: "x" });
    options(c.id);

    expect(screen.getByText(vi.options.exportHint)).toBeVisible();
    expect(screen.getByRole("button", { name: vi.options.exportMarkdown })).toHaveAccessibleDescription(
      vi.options.exportHint,
    );
  });

  it("says why when the conversation cannot be read, and lets the person try again", async () => {
    const c = backend.create({ title: "x" });
    options(c.id);
    backend.conversations.delete(c.id);

    fireEvent.click(screen.getByRole("button", { name: vi.options.exportMarkdown }));

    expect(await screen.findByRole("status")).toHaveTextContent(vi.options.exportFailed("").trim());
    expect(screen.getByRole("button", { name: vi.options.exportMarkdown })).toBeEnabled();
    expect(saved).toBeNull();
  });
});
