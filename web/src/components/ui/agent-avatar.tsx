import type { CSSProperties } from "react";

const HUES = 8;

/** A stable hue for an agent id: the same agent is the same colour on every screen. */
export function agentHue(id: string): number {
  let hash = 0;
  for (const ch of id) hash = (hash * 31 + ch.codePointAt(0)!) >>> 0;
  return (hash % HUES) + 1;
}

/** The first letter a person would say, so "trợ lý" shows T rather than a stray mark. */
export function initial(name: string): string {
  const letter = name.trim().match(/\p{L}|\p{N}/u)?.[0] ?? "?";
  return letter.toLocaleUpperCase("vi");
}

/**
 * An agent's face: its initial on a tile of its own hue. Decorative — the name is always
 * written next to it — so it is hidden from assistive technology, and the letter is drawn
 * by CSS from `data-initial` so it never joins the text of the row it sits in.
 */
export function AgentAvatar({
  id,
  name,
  size,
}: {
  id: string;
  name: string;
  size?: "sm" | "lg";
}) {
  const style = { "--avatar": `var(--hue-${agentHue(id)})` } as CSSProperties;
  return (
    <span
      className={`avatar${size ? ` ${size}` : ""}`}
      style={style}
      data-initial={initial(name)}
      aria-hidden="true"
    />
  );
}
