/** What a canvas starts with when a person makes one from the web: an empty page of text, or the
 *  smallest page, drawing and diagram that already show something once they are written into. */

import type { CreatableKind } from "../api/artifact-types";
import { vi } from "../i18n/vi";

const HTML = `<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body>

</body>
</html>
`;

const SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300">

</svg>
`;

// A kind without a template does not compile, so a kind added to `CreatableKind` cannot be left out.
const TEMPLATES: Record<CreatableKind, () => string> = {
  markdown: () => "",
  code: () => "",
  html: () => HTML,
  svg: () => SVG,
  mermaid: () => `flowchart LR\n  A[${vi.canvas.templates.start}] --> B[${vi.canvas.templates.end}]\n`,
};

/** The kinds a person can make from the web, in the order the picker lists them. */
export const CREATABLE_KINDS = Object.keys(TEMPLATES) as CreatableKind[];

export const canvasTemplate = (kind: CreatableKind): string => TEMPLATES[kind]();
