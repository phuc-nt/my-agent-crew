import { act, renderHook } from "@testing-library/react";
import { useLivePreview } from "../hooks/use-live-preview";
import { memoryStorage } from "./memory-storage";

/** Where the device keeps the choice. */
export const LIVE_PREVIEW_KEY = "canvas.livePreview";

/**
 * The preview's switch as a newly loaded page finds it: on, with nothing stored and nothing kept
 * by the tab. A choice the browser refused stays with the tab until one is stored, so the test
 * starts by making one a working browser takes. Returns that browser's storage.
 */
export function freshLivePreview(): Map<string, string> {
  const store = memoryStorage();
  const { result, unmount } = renderHook(() => useLivePreview());
  act(() => result.current.set(true));
  unmount();
  return store;
}
