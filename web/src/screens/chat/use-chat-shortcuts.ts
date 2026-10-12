import { useCallback, type Dispatch, type RefObject, type SetStateAction } from "react";
import type { CanvasDock } from "../../hooks/use-canvas-dock";
import type { useDrawer } from "../../hooks/use-drawer";
import { useShortcuts } from "../../hooks/use-shortcuts";

type Drawer = ReturnType<typeof useDrawer>;

interface ShortcutParts {
  searchRef: RefObject<HTMLInputElement | null>;
  phone: boolean;
  drawerOpen: Drawer["open"];
  showDrawer: Drawer["show"];
  hideDrawer: Drawer["hide"];
  create: () => Promise<unknown>;
  overlayOpen: boolean;
  showing: boolean;
  leaveWriting: () => void;
  closeDock: CanvasDock["close"];
  setCollapseSignal: Dispatch<SetStateAction<number>>;
}

/** The chat's keys: the search box, a new conversation, and Escape for the topmost layer. */
export function useChatShortcuts({
  searchRef,
  phone,
  drawerOpen,
  showDrawer,
  hideDrawer,
  create,
  overlayOpen,
  showing,
  leaveWriting,
  closeDock,
  setCollapseSignal,
}: ShortcutParts) {
  // The search box only exists once the list is long enough to need it, so focusing it is
  // a request that can go unanswered — hence a ref that may hold nothing. On a phone it
  // lives in the drawer, which has to open around it first. Escape closes the topmost
  // layer only: the drawer, else a canvas being written that covers the chat, else a canvas
  // covering the chat (once its typing is saved), and only then the strip under the thread.
  useShortcuts({
    onSearch: useCallback(() => {
      const box = searchRef.current;
      if (box && phone && !drawerOpen) showDrawer(box);
      else box?.focus();
    }, [phone, drawerOpen, showDrawer]),
    onNew: useCallback(() => void create(), [create]),
    onEscape: useCallback(() => {
      if (drawerOpen) hideDrawer();
      else if (overlayOpen && showing) leaveWriting();
      else if (overlayOpen) void closeDock();
      else setCollapseSignal((n) => n + 1);
    }, [drawerOpen, hideDrawer, overlayOpen, showing, leaveWriting, closeDock]),
  });
}
