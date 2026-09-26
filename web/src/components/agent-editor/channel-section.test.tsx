import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { AgentInfo } from "../../api/types";
import { vi } from "../../i18n/vi";
import { FakeBackend, fakeAgent } from "../../test/fake-backend";
import { AgentEditor } from "./agent-editor";

const agent = { ...fakeAgent, telegram: { token_env: "TG_TOKEN", chat_id: 42 } };
let backend: FakeBackend;

function open(shown: AgentInfo) {
  backend = new FakeBackend();
  backend.agents = [shown];
  vitest.stubGlobal("fetch", backend.fetch);
  render(
    <AgentEditor agent={shown} agents={[shown]} tools={[]} providers={[]} onBack={() => {}} onChanged={() => {}} />,
  );
}

describe("the Telegram chat id", () => {
  beforeEach(() => open(agent));

  // The server reads chat_id as a number; a group id is negative, and a string or a
  // half-typed "-" once reached the file as something the bot could never match.
  it("is saved as a whole number, sign included", async () => {
    const box = screen.getByLabelText(vi.editor.telegramChatId);
    await userEvent.clear(box);
    await userEvent.type(box, "-100123");
    await userEvent.click(screen.getByRole("button", { name: vi.editor.save }));

    await waitFor(() => expect(screen.getByText(vi.editor.clean)).toBeInTheDocument());
    const patch = backend.requests.find((r) => r.method === "PATCH");
    expect(patch?.body).toEqual({ profile: { telegram: { token_env: "TG_TOKEN", chat_id: -100123 } } });
    expect(screen.getByLabelText(vi.editor.telegramChatId)).toHaveValue("-100123");
  });

  it("holds the save with a message under the box while it is not a whole number", async () => {
    const box = screen.getByLabelText(vi.editor.telegramChatId);
    await userEvent.type(box, "a");

    expect(box).toHaveValue("42a");
    expect(box).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText(vi.editor.chatIdInvalid)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: vi.editor.save })).toBeDisabled();

    await userEvent.clear(box);
    expect(screen.getByText(vi.editor.chatIdInvalid)).toBeInTheDocument();
    expect(backend.requests.some((r) => r.method === "PATCH")).toBe(false);
  });
});

describe("turning the Telegram channel on", () => {
  // The box starts empty because nothing has been typed in it yet, which is not a mistake.
  it("asks for the chat id when a save is tried, not the moment the channel is on", async () => {
    open(fakeAgent);
    await userEvent.click(screen.getByRole("checkbox", { name: vi.editor.telegramEnabled }));
    await userEvent.type(screen.getByLabelText(vi.editor.telegramTokenEnv), "TG_TOKEN");
    expect(screen.queryByText(vi.editor.chatIdInvalid)).not.toBeInTheDocument();
    expect(screen.queryByTestId("save-held")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: vi.editor.save }));
    expect(screen.getByText(vi.editor.chatIdInvalid)).toBeInTheDocument();
    expect(screen.getByLabelText(vi.editor.telegramChatId)).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("button", { name: vi.editor.save })).toBeDisabled();
    expect(backend.requests.some((r) => r.method === "PATCH")).toBe(false);

    await userEvent.type(screen.getByLabelText(vi.editor.telegramChatId), "-100123");
    await userEvent.click(screen.getByRole("button", { name: vi.editor.save }));
    await waitFor(() => expect(screen.getByText(vi.editor.clean)).toBeInTheDocument());
  });
});
