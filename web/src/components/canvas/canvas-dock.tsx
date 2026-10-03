/**
 * The canvas dock beside the conversation. From 1101 px it is the right-hand column: the
 * conversation's activity as before while nothing is open, and with the list or a canvas open,
 * a tab for each over a column widened by its edge. The activity stays mounted behind its tab, so
 * its open cards and scroll survive. Narrower, the open dock covers the chat column and offers
 * the way back to it. Crossing 1101 px keeps open whatever was open, typing and all.
 *
 * Focus follows the person: opening moves it into the dock unless something there took it
 * already, a move inside the dock picks it up only when it was dropped, and closing gives it back
 * to the Canvas button when it was in the dock or nowhere. A canvas opened without being asked for
 * (quietly) leaves it where it is, even when it was nowhere: the person is typing in the chat.
 */

import { type CSSProperties, type ReactNode, type RefObject, useEffect, useRef } from "react";
import type { CanvasDock, DockView } from "../../hooks/use-canvas-dock";
import { useCanvasWidth } from "../../hooks/use-canvas-width";
import { vi } from "../../i18n/vi";
import { Icon } from "../ui/icon";
import { CanvasHandle } from "./canvas-handle";
import { CanvasPanel, type CanvasPanelProps } from "./canvas-panel";
import { CanvasPicker } from "./canvas-picker";

type Props = {
  dock: CanvasDock;
  /** A column beside the chat from 1101 px, a layer over the chat column below that. */
  mode: "column" | "overlay";
  /** The conversation's activity for the column; null where the chat shows it instead. */
  activity: ReactNode;
  connected: boolean;
  agentName(id: string): string;
  /** The Canvas button, which focus goes back to on closing. */
  trigger: RefObject<HTMLButtonElement | null>;
  /** Asks the agent about a passage of the open canvas; where it is absent, no way to ask is offered. */
  onAsk?: CanvasPanelProps["onAsk"];
  /** Why asking is off for now, if it is. */
  askDisabled?: CanvasPanelProps["askDisabled"];
};

// Every move resets "Canvas mới", and the overlay's way back, the list's first button and the
// loading panel's way to the list each come before any field.
const FIRST_CONTROL = ".dock-canvas button";

function useDockFocus(root: RefObject<HTMLDivElement | null>, trigger: Props["trigger"], view: DockView, quiet: boolean) {
  const was = useRef(view);
  useEffect(() => {
    const before = was.current;
    was.current = view;
    if (before === view) return;
    const active = document.activeElement;
    const dropped = active === null || active === document.body;
    const node = root.current;
    if (view === "closed") {
      if (dropped || node?.contains(active)) trigger.current?.focus();
    } else if (!quiet && (dropped || (before === "closed" && !node?.contains(active)))) {
      node?.querySelector<HTMLElement>(FIRST_CONTROL)?.focus();
    }
  }, [root, trigger, view, quiet]);
}

export function CanvasDockView({ dock, mode, activity, connected, agentName, trigger, onAsk, askDisabled }: Props) {
  const size = useCanvasWidth();
  const root = useRef<HTMLDivElement>(null);
  useDockFocus(root, trigger, dock.view, dock.quiet);
  const open = dock.view !== "closed";
  const column = mode === "column";
  if (!open && (!column || activity === null)) return null;

  const tabs = column && open;
  const style = tabs ? ({ "--canvas-width": `${size.width}px` } as CSSProperties) : undefined;
  // The slots below keep their places whatever shows, so nothing remounts as the tabs come and go.
  return (
    <div ref={root} className={`canvas-dock ${open ? mode : "closed"}`} style={style}>
      {tabs && <CanvasHandle {...size} />}
      {tabs && (
        <div role="tablist" className="tabs sub dock-tabs">
          {(["activity", "canvas"] as const).map((tab) => (
            <button
              key={tab}
              type="button"
              role="tab"
              id={`dock-tab-${tab}`}
              aria-controls={`dock-${tab}`}
              aria-selected={dock.tab === tab}
              className={dock.tab === tab ? "active" : ""}
              onClick={() => dock.selectTab(tab)}
            >
              {vi.canvas.tabs[tab]}
            </button>
          ))}
        </div>
      )}
      {column && (
        <div
          id="dock-activity"
          className="dock-activity"
          role={tabs ? "tabpanel" : undefined}
          aria-labelledby={tabs ? "dock-tab-activity" : undefined}
          hidden={tabs && dock.tab !== "activity"}
        >
          {activity}
        </div>
      )}
      {open && (
        <section
          id="dock-canvas"
          className="dock-canvas"
          role={tabs ? "tabpanel" : undefined}
          aria-labelledby={tabs ? "dock-tab-canvas" : undefined}
          aria-label={tabs ? undefined : vi.canvas.button}
          hidden={tabs && dock.tab !== "canvas"}
        >
          {!column && (
            <button type="button" className="ghost dock-back" onClick={() => void dock.close()}>
              {vi.canvas.backToChat}
            </button>
          )}
          {dock.view === "list" && (
            <CanvasPicker
              list={dock.list}
              creating={dock.creating}
              createFailed={dock.createFailed}
              onOpen={dock.open}
              onCreate={() => void dock.create()}
            />
          )}
          {dock.view === "canvas" && dock.artifactId !== null && (
            <CanvasPanel
              key={dock.artifactId}
              artifactId={dock.artifactId}
              created={dock.created}
              connected={connected}
              stuck={dock.stuck}
              agentName={agentName}
              bind={dock.bind}
              flush={dock.flush}
              onShowList={() => void dock.showList()}
              onClose={() => void dock.close()}
              onForceClose={dock.forceClose}
              onAsk={onAsk}
              askDisabled={askDisabled}
            />
          )}
        </section>
      )}
    </div>
  );
}

/** The way to the conversation's canvases, counted on the way; focus comes back here on closing. */
export function CanvasButton({ dock, ref }: { dock: CanvasDock; ref: Props["trigger"] }) {
  const count = dock.list.items?.length ?? 0;
  return (
    <button
      type="button"
      className="pill canvas-button"
      ref={ref}
      aria-label={vi.canvas.buttonLabel(count)}
      aria-expanded={dock.view !== "closed"}
      onClick={() => void dock.toggle()}
    >
      <Icon name="document" />
      {vi.canvas.button}
      {count > 0 && <span className="badge"> {count}</span>}
    </button>
  );
}

/** Saves handed off as another conversation opened that did not land; shown in the chat. */
export function CanvasHandoffNotices({ dock }: { dock: CanvasDock }) {
  return (
    <>
      {dock.handoffs.map((failure) => (
        <div key={failure.id} className="notice error canvas-notice" role="alert">
          <Icon name="alert" />
          <span>{vi.canvas.handoffFailed(failure.title || vi.canvas.untitled, failure.draft)}</span>
          <button type="button" className="link-button" onClick={() => dock.dismissHandoff(failure.id)}>
            {vi.canvas.dismiss}
          </button>
        </div>
      ))}
    </>
  );
}
