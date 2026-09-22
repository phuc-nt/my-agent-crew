import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../../i18n/vi";
import { FakeBackend } from "../../test/fake-backend";
import { PromptSection } from "./prompt-section";

describe("PromptSection", () => {
  let backend: FakeBackend;

  beforeEach(() => {
    backend = new FakeBackend();
    vitest.stubGlobal("fetch", backend.fetch);
  });

  it("asks for nothing until the person opens it", () => {
    const fetched = vitest.fn(backend.fetch);
    vitest.stubGlobal("fetch", fetched);
    render(<PromptSection agentId="default" />);

    // The prompt is the largest thing on the screen and the least often read; loading it
    // with the form would cost every agent open a request nobody asked for.
    expect(fetched).not.toHaveBeenCalled();
    expect(screen.queryByTestId("prompt-preview")).not.toBeInTheDocument();
  });

  it("shows what the agent is told, and how long it is", async () => {
    await backend.fetch("/api/agents/default/files/AGENTS.md", {
      method: "PUT",
      body: JSON.stringify({ content: "Luôn trả lời ngắn." }),
    });
    render(<PromptSection agentId="default" />);

    await userEvent.click(screen.getByRole("button", { name: vi.editor.promptShow }));

    const preview = await screen.findByTestId("prompt-preview");
    expect(preview).toHaveTextContent("Luôn trả lời ngắn.");
    expect(screen.getByText(vi.editor.promptChars(preview.textContent?.length ?? 0))).toBeInTheDocument();
  });

  it("re-reads on each open, so a persona saved a moment ago shows up", async () => {
    render(<PromptSection agentId="default" />);
    const toggle = () => screen.getByRole("button", { name: /Xem lời nhắc|Ẩn/ });

    await userEvent.click(toggle());
    expect(await screen.findByTestId("prompt-preview")).not.toHaveTextContent("Giọng điềm tĩnh.");
    await userEvent.click(toggle());

    await backend.fetch("/api/agents/default/files/SOUL.md", {
      method: "PUT",
      body: JSON.stringify({ content: "Giọng điềm tĩnh." }),
    });
    await userEvent.click(toggle());

    // A cached first read would still show the old prompt, which is exactly the moment
    // the person is checking whether their edit landed.
    expect(await screen.findByTestId("prompt-preview")).toHaveTextContent("Giọng điềm tĩnh.");
  });

  it("says so when the prompt cannot be read", async () => {
    vitest.stubGlobal(
      "fetch",
      vitest.fn(async () => new Response("nope", { status: 500 })),
    );
    render(<PromptSection agentId="default" />);

    await userEvent.click(screen.getByRole("button", { name: vi.editor.promptShow }));

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(vi.editor.promptFailed));
    expect(screen.queryByTestId("prompt-preview")).not.toBeInTheDocument();
  });
});
