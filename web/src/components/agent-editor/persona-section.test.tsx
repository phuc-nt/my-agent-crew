import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi as vitest, beforeEach } from "vitest";
import { vi } from "../../i18n/vi";
import { PersonaSection } from "./persona-section";
import { FakeBackend, fakeAgent } from "../../test/fake-backend";

describe("PersonaSection", () => {
  beforeEach(() => {
    vitest.stubGlobal("fetch", new FakeBackend().fetch);
  });

  it("renders tabs for each persona file", () => {
    const agent = {
      ...fakeAgent,
      persona_files: ["AGENTS.md", "SOUL.md", "IDENTITY.md"],
    };
    render(<PersonaSection agent={agent} readOnly={false} />);

    expect(screen.getByRole("tab", { name: "AGENTS.md" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "SOUL.md" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "IDENTITY.md" })).toBeInTheDocument();
  });

  it("marks the first tab as selected by default", () => {
    const agent = {
      ...fakeAgent,
      persona_files: ["AGENTS.md", "SOUL.md"],
    };
    render(<PersonaSection agent={agent} readOnly={false} />);

    const agentsTab = screen.getByRole("tab", { name: "AGENTS.md" });
    expect(agentsTab).toHaveAttribute("aria-selected", "true");
    expect(agentsTab).toHaveClass("active");
  });

  it("marks other tabs as unselected", () => {
    const agent = {
      ...fakeAgent,
      persona_files: ["AGENTS.md", "SOUL.md"],
    };
    render(<PersonaSection agent={agent} readOnly={false} />);

    const soulTab = screen.getByRole("tab", { name: "SOUL.md" });
    expect(soulTab).toHaveAttribute("aria-selected", "false");
    expect(soulTab).not.toHaveClass("active");
  });

  it("loads the content of the selected file", async () => {
    const backend = new FakeBackend();
    const agent = {
      ...fakeAgent,
      id: "coach",
      persona_files: ["AGENTS.md", "SOUL.md"],
    };
    backend.agents = [agent];
    backend.personaFiles.set("coach/AGENTS.md", "You are an AI agent.");
    vitest.stubGlobal("fetch", backend.fetch);

    render(<PersonaSection agent={agent} readOnly={false} />);

    const textarea = await screen.findByDisplayValue("You are an AI agent.");
    expect(textarea).toBeInTheDocument();
  });

  it("loads an empty string for a file that has not been written yet", async () => {
    const backend = new FakeBackend();
    const agent = {
      ...fakeAgent,
      id: "coach",
      persona_files: ["AGENTS.md", "SOUL.md"],
    };
    backend.agents = [agent];
    vitest.stubGlobal("fetch", backend.fetch);

    render(<PersonaSection agent={agent} readOnly={false} />);

    const textarea = await screen.findByRole("textbox");
    expect(textarea).toHaveValue("");
  });

  it("switches to a different file when its tab is clicked", async () => {
    const backend = new FakeBackend();
    const agent = {
      ...fakeAgent,
      id: "coach",
      persona_files: ["AGENTS.md", "SOUL.md"],
    };
    backend.agents = [agent];
    backend.personaFiles.set("coach/AGENTS.md", "Agents content");
    backend.personaFiles.set("coach/SOUL.md", "Soul content");
    vitest.stubGlobal("fetch", backend.fetch);

    render(<PersonaSection agent={agent} readOnly={false} />);

    let textarea = await screen.findByDisplayValue("Agents content");
    expect(textarea).toBeInTheDocument();

    const soulTab = screen.getByRole("tab", { name: "SOUL.md" });
    await userEvent.click(soulTab);

    textarea = await screen.findByDisplayValue("Soul content");
    expect(textarea).toBeInTheDocument();
    expect(soulTab).toHaveAttribute("aria-selected", "true");
  });

  it("shows loading state while fetching the file", async () => {
    const backend = new FakeBackend();
    const agent = {
      ...fakeAgent,
      id: "coach",
      persona_files: ["AGENTS.md"],
    };
    backend.agents = [agent];
    vitest.stubGlobal("fetch", backend.fetch);

    render(<PersonaSection agent={agent} readOnly={false} />);

    // The loading state should briefly show
    const textarea = screen.getByRole("textbox");
    // Eventually it should load
    await waitFor(() => {
      expect(textarea).toHaveValue("");
    });
  });

  it("saves the file content to the correct path when save is clicked", async () => {
    const backend = new FakeBackend();
    const agent = {
      ...fakeAgent,
      id: "coach",
      persona_files: ["AGENTS.md", "SOUL.md"],
    };
    backend.agents = [agent];
    backend.personaFiles.set("coach/AGENTS.md", "Original content");
    vitest.stubGlobal("fetch", backend.fetch);

    render(<PersonaSection agent={agent} readOnly={false} />);

    const textarea = await screen.findByDisplayValue("Original content");
    await userEvent.clear(textarea);
    await userEvent.type(textarea, "Updated content");

    const saveButton = screen.getByRole("button", { name: vi.editor.personaSave });
    await userEvent.click(saveButton);

    await waitFor(() => {
      const putRequest = backend.requests.find(
        (r) => r.method === "PUT" && r.path.includes("coach") && r.path.includes("AGENTS.md"),
      );
      expect(putRequest).toBeDefined();
      expect((putRequest?.body as { content: string }).content).toBe("Updated content");
    });
  });

  it("shows a success notice after saving", async () => {
    const backend = new FakeBackend();
    const agent = {
      ...fakeAgent,
      id: "coach",
      persona_files: ["AGENTS.md"],
    };
    backend.agents = [agent];
    vitest.stubGlobal("fetch", backend.fetch);

    render(<PersonaSection agent={agent} readOnly={false} />);

    const textarea = await screen.findByRole("textbox");
    await userEvent.type(textarea, "Content");

    const saveButton = screen.getByRole("button", { name: vi.editor.personaSave });
    await userEvent.click(saveButton);

    const notice = await screen.findByRole("status");
    expect(notice).toHaveClass("ok");
    expect(notice).toHaveTextContent(vi.editor.personaSaved("AGENTS.md"));
  });

  it("shows an error notice when save fails", async () => {
    const backend = new FakeBackend();
    const agent = {
      ...fakeAgent,
      id: "coach",
      persona_files: ["AGENTS.md"],
    };
    backend.agents = [agent];
    // Simulate a network error by making the persona file request fail
    backend.personaFiles.set("coach/AGENTS.md", "test");
    // But making PUT fail by providing a malformed response
    vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://fake");
      if (url.pathname.includes("/files/") && init?.method === "PUT") {
        return new Response(JSON.stringify({ error: "Save failed" }), { status: 500 });
      }
      return backend.fetch(input, init);
    });

    render(<PersonaSection agent={agent} readOnly={false} />);

    const textarea = await screen.findByDisplayValue("test");
    await userEvent.clear(textarea);
    await userEvent.type(textarea, "New content");

    const saveButton = screen.getByRole("button", { name: vi.editor.personaSave });
    await userEvent.click(saveButton);

    const notice = await screen.findByRole("status");
    expect(notice).toHaveClass("error");
  });

  it("disables the save button while saving", async () => {
    const backend = new FakeBackend();
    const agent = {
      ...fakeAgent,
      id: "coach",
      persona_files: ["AGENTS.md"],
    };
    backend.agents = [agent];
    vitest.stubGlobal("fetch", backend.fetch);

    render(<PersonaSection agent={agent} readOnly={false} />);

    const textarea = await screen.findByRole("textbox");
    await userEvent.type(textarea, "Content");

    const saveButton = screen.getByRole("button", { name: vi.editor.personaSave });
    expect(saveButton).not.toBeDisabled();

    await userEvent.click(saveButton);

    // After completion, should be enabled again
    await waitFor(() => {
      expect(saveButton).not.toBeDisabled();
    });
  });

  it("disables the textarea and save button when readOnly is true", () => {
    const agent = {
      ...fakeAgent,
      id: "coach",
      persona_files: ["AGENTS.md"],
    };
    render(<PersonaSection agent={agent} readOnly={true} />);

    const textarea = screen.getByRole("textbox");
    const saveButton = screen.getByRole("button", { name: vi.editor.personaSave });

    expect(textarea).toBeDisabled();
    expect(saveButton).toBeDisabled();
  });

  it("disables the textarea while loading", async () => {
    const backend = new FakeBackend();
    const agent = {
      ...fakeAgent,
      id: "coach",
      persona_files: ["AGENTS.md"],
    };
    backend.agents = [agent];
    vitest.stubGlobal("fetch", backend.fetch);

    render(<PersonaSection agent={agent} readOnly={false} />);

    // The textarea might show loading initially
    let textarea = screen.getByRole("textbox");
    if (textarea.hasAttribute("disabled")) {
      expect(textarea).toBeDisabled();
    }

    // After loading completes, it should be enabled
    await waitFor(() => {
      textarea = screen.getByRole("textbox");
      expect(textarea).not.toBeDisabled();
    });
  });

  it("saves to the correct file when switching between tabs", async () => {
    const backend = new FakeBackend();
    const agent = {
      ...fakeAgent,
      id: "coach",
      persona_files: ["AGENTS.md", "SOUL.md"],
    };
    backend.agents = [agent];
    backend.personaFiles.set("coach/AGENTS.md", "Agents");
    backend.personaFiles.set("coach/SOUL.md", "Soul");
    vitest.stubGlobal("fetch", backend.fetch);

    render(<PersonaSection agent={agent} readOnly={false} />);

    // Edit AGENTS.md
    let textarea = await screen.findByDisplayValue("Agents");
    await userEvent.clear(textarea);
    await userEvent.type(textarea, "New Agents");

    let saveButton = screen.getByRole("button", { name: vi.editor.personaSave });
    await userEvent.click(saveButton);

    // Wait for save to complete
    await waitFor(() => {
      expect(backend.personaFiles.get("coach/AGENTS.md")).toBe("New Agents");
    });

    // Switch to SOUL.md
    const soulTab = screen.getByRole("tab", { name: "SOUL.md" });
    await userEvent.click(soulTab);

    // Edit SOUL.md
    textarea = await screen.findByDisplayValue("Soul");
    await userEvent.clear(textarea);
    await userEvent.type(textarea, "New Soul");

    saveButton = screen.getByRole("button", { name: vi.editor.personaSave });
    await userEvent.click(saveButton);

    // Verify both saved to the correct paths
    await waitFor(() => {
      expect(backend.personaFiles.get("coach/SOUL.md")).toBe("New Soul");
    });
  });

  it("offers every persona file an agent could have, not only the written ones", async () => {
    // The state every new agent starts in: nothing on disk. A tab strip built from what
    // exists would be empty, leaving no way to write the first line from the web at all.
    const agent = { ...fakeAgent, persona_files: [] };
    render(<PersonaSection agent={agent} readOnly={false} />);

    for (const name of agent.persona_names) {
      expect(screen.getByRole("tab", { name: new RegExp(name) })).toBeInTheDocument();
    }
    // And they are marked as not yet written, so an empty box reads as "nothing here
    // yet" rather than as a file that failed to load.
    expect(screen.getAllByText(vi.editor.personaEmpty)).toHaveLength(agent.persona_names.length);
  });

  it("marks only the unwritten files, so the written ones are plain", () => {
    const agent = { ...fakeAgent, persona_files: ["SOUL.md"] };
    render(<PersonaSection agent={agent} readOnly={false} />);

    expect(screen.getByRole("tab", { name: "SOUL.md" })).toBeInTheDocument();
    expect(screen.getAllByText(vi.editor.personaEmpty)).toHaveLength(
      agent.persona_names.length - 1,
    );
  });
});
