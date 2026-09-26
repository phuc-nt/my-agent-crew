import { useId } from "react";
import { vi } from "../../i18n/vi";

/**
 * The product's mark: a blue tile holding one node that hands work to two others — the
 * master and its crew. It is the same drawing as the favicon and the installed-app icon,
 * so the tab, the home screen and the sidebar all show one picture.
 */
export function BrandMark({ size = 28 }: { size?: number }) {
  // Each mark needs its own gradient id: a shared one resolves to whichever copy came
  // first, and if that copy is hidden (the closed phone drawer) the others lose their fill.
  const gradient = useId();
  return (
    <svg className="brand-mark" width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <defs>
        <linearGradient id={gradient} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" style={{ stopColor: "var(--brand-from)" }} />
          <stop offset="1" style={{ stopColor: "var(--brand-to)" }} />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill={`url(#${gradient})`} />
      <g stroke="#fff" strokeWidth="2" strokeLinecap="round" opacity="0.9">
        <path d="M13.8 14.6l5.4-3.2M13.8 17.4l5.4 3.2" />
      </g>
      <g fill="#fff">
        <circle cx="11" cy="16" r="3.6" />
        <circle cx="21.8" cy="10" r="2.7" />
        <circle cx="21.8" cy="22" r="2.7" />
      </g>
    </svg>
  );
}

/** The mark with the product's name beside it, for the top of a sidebar. */
export function Brand() {
  return (
    <span className="brand">
      <BrandMark />
      <span className="brand-name">{vi.appName}</span>
    </span>
  );
}
