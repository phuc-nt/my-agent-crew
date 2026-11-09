import { useRef, useState, type ClipboardEvent, type DragEvent } from "react";
import type { Attachments } from "../hooks/use-attachments";
import { vi } from "../i18n/vi";
import { Icon } from "./ui/icon";

/** The paperclip: picks photos or files from the device, the camera included on a phone. */
export function AttachButton({ attach, disabled }: { attach: Attachments; disabled: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <button
        type="button"
        className="composer-action attach"
        aria-label={vi.attach.open}
        title={vi.attach.open}
        disabled={disabled}
        // Keeps the focus, and with it the phone's keyboard, in the box.
        onMouseDown={(event) => event.preventDefault()}
        onClick={() => input.current?.click()}
      >
        <Icon name="paperclip" />
      </button>
      <input
        ref={input}
        type="file"
        multiple
        hidden
        data-testid="attach-input"
        onChange={(event) => {
          attach.add(Array.from(event.target.files ?? []));
          // The same file picked again after removing it is still a change.
          event.target.value = "";
        }}
      />
    </>
  );
}

/** What will go with the message: thumbnails for photos, names for the rest. */
export function AttachmentTray({ attach }: { attach: Attachments }) {
  if (attach.items.length === 0) return null;
  return (
    <ul className="composer-tray" aria-label={vi.attach.tray}>
      {attach.items.map((item) => (
        <li key={item.id} className={`composer-file ${item.status}`} data-testid="composer-file" title={item.error ?? item.name}>
          {item.preview ? (
            <img src={item.preview} alt={item.name} />
          ) : (
            <span className="composer-file-name">
              <Icon name="paperclip" />
              {item.name}
            </span>
          )}
          {item.status === "uploading" && <span className="composer-file-state" aria-label={vi.attach.uploading} />}
          {item.status === "failed" && (
            <span className="composer-file-error" role="alert">
              {item.error}
            </span>
          )}
          <button type="button" className="composer-file-remove" aria-label={vi.attach.remove(item.name)} onClick={() => attach.remove(item.id)}>
            <Icon name="close" />
          </button>
        </li>
      ))}
    </ul>
  );
}

const hasFiles = (event: DragEvent) => Array.from(event.dataTransfer.types).includes("Files");

/** Paste and drop for the composer: a screenshot pasted or a photo dragged in joins the tray. */
export function useFileIntake(attach: Attachments, enabled: boolean) {
  const [over, setOver] = useState(false);
  const onPaste = (event: ClipboardEvent) => {
    const files = Array.from(event.clipboardData.files);
    if (!enabled || files.length === 0) return;
    // Text copied with a picture still pastes as text; only a bare file stops it.
    if (!event.clipboardData.getData("text/plain")) event.preventDefault();
    attach.add(files);
  };
  const drop = {
    onDragOver: (event: DragEvent) => {
      if (!enabled || !hasFiles(event)) return;
      event.preventDefault();
      setOver(true);
    },
    onDragLeave: (event: DragEvent) => {
      if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOver(false);
    },
    onDrop: (event: DragEvent) => {
      setOver(false);
      if (!enabled || !hasFiles(event)) return;
      event.preventDefault();
      attach.add(Array.from(event.dataTransfer.files));
    },
  };
  return { over, onPaste, drop };
}
