import { useEffect, useRef, useState } from "react";
import { vi } from "../i18n/vi";
import { MemoryEditor } from "./memory-editor";

interface Props {
  onReadNote: (day: string) => Promise<string>;
  onSaveNote: (day: string, body: string) => Promise<void>;
  onDirtyChange?: (dirty: boolean) => void;
}

/**
 * The note file for the viewer's own today, `YYYY-MM-DD` on their calendar.
 *
 * Not the UTC date: at 06:30 in Hà Nội it is still yesterday in UTC, and a note written
 * over breakfast would land in the day before, where nobody would look for it.
 */
export function localDay(now: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/**
 * A quick way to jot something down for the wiki to compile later, without going through
 * the agent tab and finding today in the list of notes.
 *
 * It reads the note once, when it opens. The parent mounts one per agent, so a note read
 * for one vault is never saved into another.
 */
export function WikiTodayNote({ onReadNote, onSaveNote, onDirtyChange }: Props) {
  // Fixed when the note opens, so a save just after midnight lands where it was read from.
  const [day] = useState(() => localDay());
  const [text, setText] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const read = useRef(onReadNote);
  useEffect(() => {
    read.current = onReadNote;
  });

  useEffect(() => {
    let live = true;
    read.current(day).then(
      (body) => live && setText(body),
      () => live && setFailed(true),
    );
    return () => {
      live = false;
    };
  }, [day]);

  if (failed) {
    return (
      <p className="notice error" role="alert">
        {vi.loadFailed}
      </p>
    );
  }
  if (text === null) return <p className="muted">{vi.loading}</p>;
  return (
    <div className="wiki-today-note">
      <MemoryEditor
        label={vi.wiki.todayNoteLabel(day)}
        value={text}
        rows={6}
        onDirtyChange={onDirtyChange}
        onSave={async (next) => {
          await onSaveNote(day, next);
          setText(next);
        }}
      />
    </div>
  );
}
