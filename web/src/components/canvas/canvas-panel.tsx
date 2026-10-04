/**
 * One canvas beside the chat: its name, its version and save line, the text to read or edit, its
 * history, and copy and download. A canvas an agent wrote opens to read and a person's opens to
 * edit. The mode is chosen once, when the text first arrives, so a version arriving later never
 * moves the person from one to the other.
 *
 * Where the panel is given a way to ask, a passage selected in the text can be asked about from a
 * bar at its foot. The passage is the one selected when the text last stood as it does now: any
 * change to the text, and a turn to the other mode or to the history, drops it.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { MessageCanvas } from "../../api/artifact-types";
import { useCanvas } from "../../hooks/use-canvas";
import type { PanelHandle } from "../../hooks/use-canvas-dock";
import { useCanvasRename } from "../../hooks/use-canvas-rename";
import { useSaveThenShow } from "../../hooks/use-save-then-show";
import { vi } from "../../i18n/vi";
import { hasNoText, showsSaved } from "../../lib/canvas-kinds";
import type { CanvasState } from "../../lib/canvas-machine";
import type { CanvasSelection } from "../../lib/canvas-selection";
import { isDirty } from "../../lib/canvas-state";
import type { SendResult } from "../../lib/send-result";
import { type AskDisabled, CanvasAsk } from "./canvas-ask";
import { CanvasConflict } from "./canvas-conflict";
import { CanvasEditor } from "./canvas-editor";
import { type CanvasMode, CanvasHeader } from "./canvas-header";
import { CanvasHistory } from "./canvas-history";
import { CanvasSavedView } from "./canvas-saved-view";
import { CanvasNotices } from "./canvas-status";
import { CanvasView } from "./canvas-view";

export type CanvasPanelProps = {
  artifactId: string;
  /** Just made from the web: its name opens ready to type over, and its text to edit. */
  created: boolean;
  /** The activity stream is up; the canvas is read again each time it comes back. */
  connected: boolean;
  /** Leaving was asked for and no save landed. */
  stuck: boolean;
  agentName(id: string): string;
  /** Lets the dock save the text and ask whether the canvas is gone or its person is typing; returns the unbind. */
  bind(handle: PanelHandle): () => void;
  /** The dock's flush, with its time limit. */
  flush(): Promise<number | null>;
  onShowList(): void;
  onClose(): void;
  onForceClose(): void;
  /** Asks the agent about a passage of this canvas; where it is absent, no way to ask is offered. */
  onAsk?(canvas: MessageCanvas, question: string): Promise<SendResult>;
  /** Why asking is off for now, if it is. */
  askDisabled?: AskDisabled;
};

/** A person's text opens to edit, an agent's to read, unless the canvas was just made here or this
 *  device holds typing for it. A canvas with no text opens to look at. */
function firstMode(state: CanvasState, created: boolean): CanvasMode {
  if (hasNoText(state.summary?.kind ?? "")) return "view";
  if (created || state.opened !== "fresh") return "edit";
  return state.base.author.startsWith("agent:") ? "view" : "edit";
}

export function CanvasPanel(props: CanvasPanelProps) {
  const { artifactId, created, connected, stuck, agentName, bind, flush, onShowList, onClose, onForceClose } = props;
  const { onAsk, askDisabled = null } = props;
  const canvas = useCanvas(artifactId, connected);
  const { state } = canvas;
  const latest = useRef(state);
  latest.current = state;
  const draftFailed = useRef(canvas.draftFailed);
  draftFailed.current = canvas.draftFailed;
  const editor = useRef<HTMLTextAreaElement | null>(null);
  const [chosen, setChosen] = useState<CanvasMode | null>(null);
  const [history, setHistory] = useState(false);
  const { rename, renameError } = useCanvasRename(artifactId, canvas);
  const [picked, setPicked] = useState<{ selection: CanvasSelection; gen: number } | null>(null);
  const pick = useCallback(
    (selection: CanvasSelection | null) => setPicked(selection && { selection, gen: latest.current.gen }),
    [],
  );

  // The handle is one object for as long as the panel stays: what changes is read through the refs.
  useEffect(
    () =>
      bind({
        flush: canvas.flush,
        gone: () => latest.current.gone,
        typing: () => isDirty(latest.current) || (editor.current !== null && document.activeElement === editor.current),
        waitMs: canvas.waitMs,
        draftFailed: () => draftFailed.current,
      }),
    [bind, canvas.flush, canvas.waitMs],
  );

  if (chosen === null && state.phase === "ready") setChosen(firstMode(state, created));

  const ready = state.phase === "ready";
  const kind = state.summary?.kind ?? "markdown";
  const saved = showsSaved(kind);
  const { waiting, turn, cancel } = useSaveThenShow(flush);

  // A page and a picture show what the server holds, so turning to them first saves what was typed.
  const choose = (mode: CanvasMode) =>
    turn(mode === "view" && saved && isDirty(latest.current), () => {
      setChosen(mode);
      setHistory(false);
      setPicked(null);
    });

  const showHistory = ready && history && !state.gone;
  const selection = picked?.gen === state.gen ? picked.selection : null;
  return (
    <div className="canvas-panel">
      <CanvasHeader
        canvas={canvas}
        artifactId={artifactId}
        created={created}
        agentName={agentName}
        mode={chosen}
        switching={waiting}
        history={history}
        onChoose={choose}
        onHistory={() => {
          // Opening the history is a move of its own: a turn still waiting for its save must not close it.
          cancel();
          setHistory(!history);
          setPicked(null);
        }}
        onRename={(title) => void rename(title)}
        onShowList={onShowList}
        onClose={onClose}
      />
      <div className="canvas-body">
        <CanvasNotices canvas={canvas} stuck={stuck} onForceClose={onForceClose} />
        {renameError && (
          <div className="notice error canvas-notice" role="alert">
            {vi.canvas.renameFailed(renameError)}
          </div>
        )}
        {state.phase === "loading" && <p className="muted">{vi.canvas.loading}</p>}
        {showHistory && (
          <CanvasHistory
            canvas={canvas}
            artifactId={artifactId}
            agentName={agentName}
            flush={flush}
            onClose={() => setHistory(false)}
          />
        )}
        {ready && !showHistory && (
          <>
            <CanvasConflict canvas={canvas} agentName={agentName} />
            {chosen !== "view" ? (
              <CanvasEditor canvas={canvas} kind={kind} fieldRef={editor} onSelection={onAsk ? pick : undefined} />
            ) : saved ? (
              <CanvasSavedView
                canvas={canvas}
                artifactId={artifactId}
                kind={kind}
                connected={connected}
                askDisabled={askDisabled}
                flush={flush}
                onAsk={onAsk}
              />
            ) : (
              <CanvasView text={state.text} kind={kind} onSelection={onAsk ? pick : undefined} />
            )}
          </>
        )}
      </div>
      {onAsk && (
        <CanvasAsk
          artifactId={artifactId}
          selection={selection}
          gen={state.gen}
          // A page or a picture has no text to select a passage of.
          hidden={showHistory || state.gone || state.conflict !== null || (chosen === "view" && saved)}
          disabled={askDisabled}
          flush={flush}
          onAsk={onAsk}
          onAsked={() => setPicked(null)}
        />
      )}
    </div>
  );
}
