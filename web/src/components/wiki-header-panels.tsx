import { useId, useState } from "react";
import type { WikiReport } from "../api/types";
import { vi } from "../i18n/vi";
import { WikiQuestions } from "./wiki-questions";
import { WikiTodayNote } from "./wiki-today-note";

interface Props {
  agentId: string;
  questions: WikiReport["questions"];
  titles: ReadonlyMap<string, string>;
  onOpen: (slug: string) => void;
  onReadNote: (day: string) => Promise<string>;
  onSaveNote: (day: string, body: string) => Promise<void>;
}

/** What the header row has opened below it; tied to the agent it was opened for. */
type Panel = { agentId: string; kind: "questions" | "note" };

/**
 * The toggles above a vault's list and the one panel they have open: the questions the
 * vault still has, or today's note.
 *
 * Closing the note unmounts its editor, so a line typed and not yet saved is asked about
 * before it goes, whichever toggle closes it.
 */
export function WikiHeaderPanels({ agentId, questions, titles, onOpen, onReadNote, onSaveNote }: Props) {
  const [panel, setPanel] = useState<Panel | null>(null);
  const [noteDirty, setNoteDirty] = useState(false);
  // Switching agent closes the panel rather than showing the new vault in the old one's place.
  const shown = panel?.agentId === agentId ? panel.kind : null;
  const questionsId = useId();
  const noteId = useId();

  const toggle = (kind: Panel["kind"]) => {
    if (shown === "note" && noteDirty && !window.confirm(vi.wiki.discardEdit)) return;
    setPanel(shown === kind ? null : { agentId, kind });
  };

  return (
    <>
      <div className="wiki-header-actions">
        {questions.length > 0 && (
          <button
            type="button"
            className="ghost"
            aria-expanded={shown === "questions"}
            aria-controls={shown === "questions" ? questionsId : undefined}
            onClick={() => toggle("questions")}
          >
            {vi.wiki.openQuestions(questions.length)}
          </button>
        )}
        <button
          type="button"
          className="ghost"
          aria-expanded={shown === "note"}
          aria-controls={shown === "note" ? noteId : undefined}
          onClick={() => toggle("note")}
        >
          {vi.wiki.todayNote}
        </button>
      </div>
      {shown === "questions" && <WikiQuestions id={questionsId} questions={questions} titles={titles} onOpen={onOpen} />}
      {shown === "note" && (
        <div id={noteId}>
          <WikiTodayNote key={agentId} onReadNote={onReadNote} onSaveNote={onSaveNote} onDirtyChange={setNoteDirty} />
        </div>
      )}
    </>
  );
}
