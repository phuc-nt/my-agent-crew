import { useEffect, useState } from "react";

/**
 * Whether a CSS media query matches, followed live as the window is resized.
 *
 * Layout that changes which component renders (not just how it looks) needs the answer in
 * JavaScript; CSS alone would mount both and hide one. A browser or test runner without
 * `matchMedia` answers false, so callers should make `false` the safe, narrow layout.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => currentMatch(query));

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const list = window.matchMedia(query);
    const update = () => setMatches(list.matches);
    // The query may have changed between the first render and this effect.
    update();
    list.addEventListener("change", update);
    return () => list.removeEventListener("change", update);
  }, [query]);

  return matches;
}

function currentMatch(query: string): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia(query).matches;
}
