import { useCallback, useEffect, useRef, useState } from "react";
import { uploadToInbox } from "../api/client/inbox";
import { vi } from "../i18n/vi";
import type { SendWords } from "./use-send-lock";

/** What the server takes in one file (`MAX_UPLOAD_BYTES` in routes_inbox_upload.py). */
export const MAX_UPLOAD_MB = 20;

export interface Attachment {
  id: number;
  name: string;
  /** A picture of the file while it is in the box; null for anything not an image. */
  preview: string | null;
  status: "uploading" | "ready" | "failed";
  /** The attachment line to send, once the server has the file. */
  line?: string;
  error?: string;
}

/** The message as the agent reads it: the files first, then the words, as Telegram sends it. */
export function withAttachments(lines: string[], words: string): string {
  return [...lines, words].filter((part) => part !== "").join("\n");
}

/**
 * The files the person adds to the next message. Each goes to the agent's inbox the moment
 * it is added, so sending only waits for an upload still under way. The tray belongs to one
 * draft: going to another conversation drops it, since the files sit in that agent's inbox.
 */
export function useAttachments(agentId: string | undefined, draftKey: string | null) {
  const [items, setItems] = useState<Attachment[]>([]);
  const next = useRef(0);
  const live = useRef<Attachment[]>([]);
  live.current = items;

  const patch = (id: number, change: Partial<Attachment>) =>
    setItems((all) => all.map((item) => (item.id === id ? { ...item, ...change } : item)));

  const add = useCallback(
    (files: File[]) => {
      if (!agentId) return;
      const added = files.map((file): Attachment & { file: File } => ({
        id: ++next.current,
        name: file.name || "file",
        preview: file.type.startsWith("image/") ? URL.createObjectURL(file) : null,
        status: file.size > MAX_UPLOAD_MB * 1024 * 1024 ? "failed" : "uploading",
        error: file.size > MAX_UPLOAD_MB * 1024 * 1024 ? vi.attach.tooLarge(MAX_UPLOAD_MB) : undefined,
        file,
      }));
      setItems((all) => [...all, ...added.map(({ file: _file, ...item }) => item)]);
      for (const item of added) {
        if (item.status !== "uploading") continue;
        uploadToInbox(agentId, item.file).then(
          (saved) => patch(item.id, { status: "ready", line: saved.line }),
          (error: unknown) =>
            patch(item.id, { status: "failed", error: vi.attach.failed(error instanceof Error ? error.message : String(error)) }),
        );
      }
    },
    [agentId],
  );

  const remove = useCallback((id: number) => {
    const gone = live.current.find((item) => item.id === id);
    if (gone?.preview) URL.revokeObjectURL(gone.preview);
    setItems((all) => all.filter((item) => item.id !== id));
  }, []);

  const clear = useCallback(() => {
    for (const item of live.current) if (item.preview) URL.revokeObjectURL(item.preview);
    setItems([]);
  }, []);

  // Another conversation, or the box going away, takes the tray with it.
  useEffect(() => clear, [agentId, draftKey, clear]);

  const lines = items.flatMap((item) => (item.status === "ready" && item.line ? [item.line] : []));

  /** `onSend` with the files ahead of the words; they leave the tray once the message was taken. */
  const carry =
    (onSend: SendWords): SendWords =>
    (words) => {
      const answer = onSend(withAttachments(lines, words));
      if (!(answer instanceof Promise)) return void clear();
      return answer.then((spent) => (spent && clear(), spent));
    };

  return {
    items,
    carry,
    add,
    remove,
    clear,
    uploading: items.some((item) => item.status === "uploading"),
    lines,
  };
}

export type Attachments = ReturnType<typeof useAttachments>;
