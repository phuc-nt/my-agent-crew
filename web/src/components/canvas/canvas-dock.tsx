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
 *
 * A canvas the agent is still writing stands in the dock before whatever the dock holds, which
 * waits behind it unseen and unchanged; with nothing held, the dock shows for it all the same. It
 * never moves the keyboard by coming up, and once it goes the keyboard is picked up only when it
 * went with it.
 */

import { type CSSProperties, type ReactNode, type RefObject, useEffect, useRef } from "react";
import type { CanvasDock, DockView } from "../../hooks/use-canvas-dock";
import { useCanvasWidth } from "../../hooks/use-canvas-width";
import { routeHash } from "../../hooks/use-route";
import { vi } from "../../i18n/vi";
import { dockShowing } from "../../lib/canvas-dock-state";
import type { WritingItem } from "../../lib/canvas-writing";
import { CanvasHandle } from "./canvas-handle";
import { CanvasPanel, type CanvasPanelProps } from "./canvas-panel";
import { CanvasPicker } from "./canvas-picker";
import { CanvasWritingView } from "./canvas-writing-view";

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
  /** The canvas the agent is writing that the dock shows; `asked` counts the person's requests for it. */
  writing?: { item: WritingItem; asked: number | null; onLeave(): void } | null;
};

// Every move resets "Canvas mới", and the overlay's way back, the list's first button and the
// loading panel's way to the list each come before any field.
const FIRST_CONTROL = ".dock-canvas button";

type Shown = DockView | "writing";

function useDockFocus(root: RefObject<HTMLDivElement | null>, trigger: Props["trigger"], view: Shown, quiet: boolean) {
  const was = useRef(view);
  useEffect(() => {
    const before = was.current;
    was.current = view;
    if (before === view) return;
    const active = document.activeElement;
    const dropped = active === null || active === document.body;
    const node = root.current;
    if (view === "closed") {
      // The activity shows again where the canvas being written stood: the keyboard may be in it.
      if (dropped || (before !== "writing" && node?.contains(active))) trigger.current?.focus();
    } else if ((!quiet || before === "writing") && (dropped || (before === "closed" && !node?.contains(active)))) {
      node?.querySelector<HTMLElement>(FIRST_CONTROL)?.focus();
    }
  }, [root, trigger, view, quiet]);
}

export function CanvasDockView({ dock, mode, activity, connected, agentName, trigger, onAsk, askDisabled, writing }: Props) {
  const size = useCanvasWidth();
  // The dock looks in its own element to learn whether the person has the keyboard there.
  const root = dock.box;
  const showing = writing != null;
  useDockFocus(root, trigger, showing ? "writing" : dock.view, showing || dock.quiet);
  const open = dockShowing(dock.view, showing);
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
            <button type="button" className="ghost dock-back" onClick={() => (writing ? writing.onLeave() : void dock.close())}>
              {vi.canvas.backToChat}
            </button>
          )}
          {writing && <CanvasWritingView key={writing.item.key} item={writing.item} asked={writing.asked} onLeave={writing.onLeave} />}
          {/* What the dock holds keeps its place behind a canvas being written, typing and all. */}
          <div className="dock-held" hidden={showing}>
            {dock.view === "list" && (
              <CanvasPicker
                list={dock.list}
                creating={dock.creating}
                createFailed={dock.createFailed}
                onOpen={dock.open}
                onCreate={(kind) => void dock.create(kind)}
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
                standaloneHref={routeHash({ kind: "manage", section: "canvas", param: dock.artifactId })}
                onAsk={onAsk}
                askDisabled={askDisabled}
              />
            )}
          </div>
        </section>
      )}
    </div>
  );
}
