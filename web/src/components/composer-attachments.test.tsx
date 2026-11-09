import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { withAttachments } from "../hooks/use-attachments";
import { vi } from "../i18n/vi";
import { memoryStorage } from "../test/memory-storage";
import { Composer } from "./composer";

const line = (path: string) => `[${vi.attachmentSaved}: ${path}]`;

/** The inbox route, answered at once or by hand. */
function inbox(hold = false) {
  const calls: { url: string; init: RequestInit }[] = [];
  let release: () => void = () => undefined;
  const fetch = vitest.fn(async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    if (hold) await new Promise<void>((resolve) => (release = resolve));
    const name = new URL(url, "http://x").searchParams.get("name");
    return new Response(JSON.stringify({ path: `/w/inbox/${name}`, line: line(`/w/inbox/${name}`) }), { status: 201 });
  });
  vitest.stubGlobal("fetch", fetch);
  return { calls, release: () => act(async () => release()) };
}

beforeEach(() => {
  memoryStorage();
  URL.createObjectURL = vitest.fn(() => "blob:preview");
  URL.revokeObjectURL = vitest.fn();
});

afterEach(() => {
  vitest.restoreAllMocks();
  vitest.unstubAllGlobals();
});

function composer(onSend: (text: string) => Promise<boolean> | void, agentId: string | null = "master") {
  return <Composer disabled={false} busy={false} draftKey="c1" agentId={agentId ?? undefined} onSend={onSend} onStop={() => undefined} />;
}

const box = () => screen.getByRole("textbox", { name: vi.composerPlaceholder });
const photo = (name = "anh.png", size = 10) => new File([new Uint8Array(size)], name, { type: "image/png" });
const pick = (...files: File[]) => userEvent.upload(screen.getByTestId("attach-input"), files);

describe("files sent from the composer", () => {
  it("uploads a picked photo to the agent's inbox and sends its line ahead of the words", async () => {
    const server = inbox();
    const onSend = vitest.fn();
    render(composer(onSend));
    await pick(photo());
    await waitFor(() => expect(screen.getByTestId("composer-file")).toHaveClass("ready"));
    expect(server.calls[0].url).toBe("/api/agents/master/inbox?name=anh.png");
    expect(server.calls[0].init.method).toBe("POST");

    await userEvent.type(box(), "xem ảnh này{Enter}");
    expect(onSend).toHaveBeenCalledWith(`${line("/w/inbox/anh.png")}\nxem ảnh này`);
    expect(screen.queryByTestId("composer-file")).toBeNull();
  });

  it("sends a photo with no words at all", async () => {
    inbox();
    const onSend = vitest.fn();
    render(composer(onSend));
    await pick(photo());
    await waitFor(() => expect(screen.getByRole("button", { name: vi.send })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: vi.send }));
    expect(onSend).toHaveBeenCalledWith(line("/w/inbox/anh.png"));
  });

  it("does not send while a file is still going up", async () => {
    const server = inbox(true);
    const onSend = vitest.fn();
    render(composer(onSend));
    await pick(photo());
    await userEvent.type(box(), "chờ{Enter}");
    expect(onSend).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: vi.send })).toBeDisabled();

    await server.release();
    await waitFor(() => expect(screen.getByRole("button", { name: vi.send })).toBeEnabled());
  });

  it("keeps the files when the message was not taken, and drops them once it was", async () => {
    inbox();
    let answer: (spent: boolean) => void = () => undefined;
    const onSend = vitest.fn(() => new Promise<boolean>((resolve) => (answer = resolve)));
    render(composer(onSend));
    await pick(photo());
    await waitFor(() => expect(screen.getByTestId("composer-file")).toHaveClass("ready"));

    await userEvent.type(box(), "một{Enter}");
    await act(async () => answer(false));
    expect(screen.getByTestId("composer-file")).toBeInTheDocument();

    await userEvent.keyboard("{Enter}");
    await act(async () => answer(true));
    expect(screen.queryByTestId("composer-file")).toBeNull();
  });

  it("says why a file did not go up and lets it be removed", async () => {
    vitest.stubGlobal("fetch", vitest.fn(async () => new Response(JSON.stringify({ detail: "hỏng" }), { status: 500 })));
    render(composer(vitest.fn()));
    await pick(photo());
    expect(await screen.findByRole("alert")).toHaveTextContent(vi.attach.failed("hỏng"));
    expect(screen.getByRole("button", { name: vi.send })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: vi.attach.remove("anh.png") }));
    expect(screen.queryByTestId("composer-file")).toBeNull();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:preview");
  });

  it("refuses a file over the limit without sending it anywhere", async () => {
    const server = inbox();
    render(composer(vitest.fn()));
    await pick(photo("to.png", 21 * 1024 * 1024));
    expect(await screen.findByRole("alert")).toHaveTextContent(vi.attach.tooLarge(20));
    expect(server.calls).toHaveLength(0);
  });

  it("takes a pasted screenshot into the tray", async () => {
    inbox();
    render(composer(vitest.fn()));
    fireEvent.paste(box(), { clipboardData: { files: [photo("image.png")], getData: () => "" } });
    await waitFor(() => expect(screen.getByTestId("composer-file")).toHaveClass("ready"));
  });

  it("takes a file dropped on the composer", async () => {
    inbox();
    const { container } = render(composer(vitest.fn()));
    const form = container.querySelector("form")!;
    const dataTransfer = { types: ["Files"], files: [photo("keo.png")] };
    fireEvent.dragOver(form, { dataTransfer });
    expect(form).toHaveClass("dropping");
    fireEvent.drop(form, { dataTransfer });
    expect(form).not.toHaveClass("dropping");
    await waitFor(() => expect(screen.getByTestId("composer-file")).toHaveClass("ready"));
  });

  it("offers no paperclip when no agent would take the file", () => {
    render(composer(vitest.fn(), null));
    expect(screen.queryByRole("button", { name: vi.attach.open })).toBeNull();
  });

  it("puts the files first and leaves out empty words", () => {
    expect(withAttachments(["[a]", "[b]"], "chữ")).toBe("[a]\n[b]\nchữ");
    expect(withAttachments(["[a]"], "")).toBe("[a]");
    expect(withAttachments([], "chữ")).toBe("chữ");
  });
});
