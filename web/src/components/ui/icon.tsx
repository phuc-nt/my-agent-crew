import type { ReactNode } from "react";

/**
 * The app's line icons, drawn on a 24px grid with one stroke weight so they sit together
 * the way letters of one typeface do. Emoji used to fill this role; they render as a
 * different picture on every platform and in colour the theme cannot reach, which is
 * exactly what an icon beside a label must not do.
 *
 * Icons are always decorative here — the label beside them carries the meaning — so they
 * are hidden from assistive technology. A control that is only an icon names itself with
 * `aria-label` on the control.
 */
const PATHS = {
  plus: <path d="M12 5v14M5 12h14" />,
  close: <path d="M6.5 6.5l11 11M17.5 6.5l-11 11" />,
  menu: <path d="M4 7h16M4 12h16M4 17h10" />,
  "chevron-left": <path d="M14.5 6l-6 6 6 6" />,
  "chevron-right": <path d="M9.5 6l6 6-6 6" />,
  "chevron-down": <path d="M6 9.5l6 6 6-6" />,
  "arrow-up": <path d="M12 19V5M6 11l6-6 6 6" />,
  "arrow-down": <path d="M12 5v14M6 13l6 6 6-6" />,
  "arrow-right": <path d="M5 12h14M13 6l6 6-6 6" />,
  stop: <rect x="7" y="7" width="10" height="10" rx="2.2" fill="currentColor" stroke="none" />,
  activity: <path d="M3 12h3.5l2.5-6.5 5 13 2.5-6.5H21" />,
  approvals: (
    <>
      <path d="M12 3.2l7 2.6v5.6c0 4.4-2.9 7.9-7 9.4-4.1-1.5-7-5-7-9.4V5.8z" />
      <path d="M9 12.2l2.1 2.1L15.2 10" />
    </>
  ),
  coins: (
    <>
      <circle cx="12" cy="12" r="8.6" />
      <path d="M14.8 9.4c-.6-.9-1.6-1.4-2.8-1.4-1.6 0-2.8.8-2.8 2 0 2.8 5.8 1.4 5.8 4.1 0 1.2-1.3 2-3 2-1.2 0-2.3-.5-2.9-1.4M12 6.4V8M12 16v1.6" />
    </>
  ),
  users: (
    <>
      <circle cx="9" cy="8.5" r="3.3" />
      <path d="M3 19.5c.6-3.2 3-5.2 6-5.2s5.4 2 6 5.2" />
      <path d="M15.5 5.4a3.3 3.3 0 0 1 0 6.3M17.6 14.6c1.8.7 3 2.5 3.4 4.9" />
    </>
  ),
  wrench: (
    <g transform="rotate(45 12 12)">
      <path d="M10 2.6v3.6h4V2.6a4.6 4.6 0 1 1-4 0z" />
      <path d="M10.6 11.1v8.6a1.4 1.4 0 0 0 2.8 0v-8.6" />
    </g>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="8.6" />
      <path d="M12 7.5V12l3 2" />
    </>
  ),
  book: (
    <>
      <path d="M12 6.5C10.6 5.3 8.6 4.6 6 4.6c-.9 0-1.8.1-2.5.3v13.7c.7-.2 1.6-.3 2.5-.3 2.6 0 4.6.7 6 1.9" />
      <path d="M12 6.5c1.4-1.2 3.4-1.9 6-1.9.9 0 1.8.1 2.5.3v13.7c-.7-.2-1.6-.3-2.5-.3-2.6 0-4.6.7-6 1.9z" />
    </>
  ),
  plug: <path d="M9 3v4M15 3v4M6.5 7h11v3.5a5.5 5.5 0 0 1-11 0zM12 16v5" />,
  sliders: (
    <>
      <path d="M4 7h9M17 7h3M4 12h3M11 12h9M4 17h11M19 17h1" />
      <circle cx="15" cy="7" r="2" />
      <circle cx="9" cy="12" r="2" />
      <circle cx="17" cy="17" r="2" />
    </>
  ),
  handoff: (
    <>
      <circle cx="6" cy="12" r="2.4" />
      <circle cx="18" cy="6" r="2.4" />
      <circle cx="18" cy="18" r="2.4" />
      <path d="M8.2 11l7.6-4M8.2 13l7.6 4" />
    </>
  ),
  bolt: <path d="M13 2.8L5 13.4h6.2L10.6 21.2 19 10.4h-6.3z" />,
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  help: (
    <>
      <circle cx="12" cy="12" r="8.6" />
      <path d="M9.6 9.5a2.5 2.5 0 1 1 3.4 2.3c-.6.3-1 .8-1 1.5v.5M12 16.8v.1" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="8.6" />
      <path d="M12 11v5.2M12 7.8v.1" />
    </>
  ),
  steps: <path d="M9 6.5h11M9 12h11M9 17.5h11M4.5 6.5h.1M4.5 12h.1M4.5 17.5h.1" />,
  chip: (
    <>
      <rect x="6.5" y="6.5" width="11" height="11" rx="2.2" />
      <path d="M10 3.5v3M14 3.5v3M10 17.5v3M14 17.5v3M3.5 10h3M3.5 14h3M17.5 10h3M17.5 14h3" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="6.4" />
      <path d="M20 20l-4.4-4.4" />
    </>
  ),
  "corner-down-right": <path d="M6 5v6.5a3 3 0 0 0 3 3h9M14.5 11l3.5 3.5-3.5 3.5" />,
  download: <path d="M12 4v11M7 10.5l5 5 5-5M5 20h14" />,
  message: (
    <path d="M20 14.5a2.5 2.5 0 0 1-2.5 2.5H9l-4.5 3.5V6.5A2.5 2.5 0 0 1 7 4h10.5A2.5 2.5 0 0 1 20 6.5z" />
  ),
  edit: <path d="M4.5 19.5h4l10-10a2.1 2.1 0 0 0-3-3l-10 10zM13.8 7.8l2.9 2.9" />,
  trash: (
    <path d="M4.5 7h15M9.5 7V4.8h5V7M6.5 7l.8 12.2a1.5 1.5 0 0 0 1.5 1.3h6.4a1.5 1.5 0 0 0 1.5-1.3L17.5 7M10.2 11v5.5M13.8 11v5.5" />
  ),
  play: <path d="M8 5.5v13l10.5-6.5z" />,
  refresh: <path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3M19.5 4.5v4h-4" />,
  alert: <path d="M12 4l9 15.5H3zM12 10v4.2M12 16.9v.1" />,
  pause: <path d="M9 6.5v11M15 6.5v11" />,
  spinner: <path d="M12 3.5a8.5 8.5 0 1 1-8.5 8.5" />,
  key: (
    <>
      <circle cx="8" cy="15" r="3.8" />
      <path d="M10.7 12.3L19 4M16 7l2.5 2.5M13.5 9.5l2 2" />
    </>
  ),
  grid: (
    <>
      <rect x="4" y="4" width="6.5" height="6.5" rx="1.8" />
      <rect x="13.5" y="4" width="6.5" height="6.5" rx="1.8" />
      <rect x="4" y="13.5" width="6.5" height="6.5" rx="1.8" />
      <rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.8" />
    </>
  ),
  sparkle: (
    <path d="M12 3.5l1.8 5.1 5.2 1.9-5.2 1.9L12 17.5l-1.8-5.1L5 10.5l5.2-1.9zM18.5 16l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z" />
  ),
} satisfies Record<string, ReactNode>;

export type IconName = keyof typeof PATHS;

export function Icon({ name, className = "" }: { name: IconName; className?: string }) {
  return (
    <svg
      className={`icon ${className}`.trim()}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[name]}
    </svg>
  );
}
