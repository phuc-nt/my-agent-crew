/**
 * The agent's reply as formatted prose.
 *
 * Models write markdown whether or not anyone asked them to, so rendering it
 * raw means the reader sees `**bold**` and pipe-drawn tables instead of the
 * text the model meant to write. Only the assistant's words go through here:
 * what the person typed is shown exactly as they typed it, because someone who
 * writes an asterisk means an asterisk.
 *
 * Raw HTML in the source is escaped rather than rendered — `rehype-raw` is
 * deliberately absent. A reply is partly built from tool output and web pages,
 * so treating it as markup would let a fetched page put its own elements in the
 * thread. For the same reason an image served from elsewhere loads only when asked.
 */

import { isValidElement, type ReactNode, useMemo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { vi } from "../i18n/vi";
import { remarkHiddenChars } from "../lib/hidden-chars";
import { remarkWikiLinks, wikiSlugFromHref } from "../lib/wiki-links";
import { CopyButton } from "./copy-button";
import { MarkdownImage } from "./markdown-image";

/** Links leave the app, so they open away from the conversation and cannot reach it. */
function SafeLink({ href, children }: { href?: string; children?: React.ReactNode }) {
  if (!href) return <span>{children}</span>;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  );
}

/** The characters a rendered node spells, which is what copying a code block should take. */
function plainText(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(plainText).join("");
  if (isValidElement<{ children?: ReactNode }>(node)) return plainText(node.props.children);
  return "";
}

/**
 * Fenced blocks get a scrollable `<pre>` with a copy corner of its own, so a command in
 * a reply can be taken without the prose around it; an inline span stays inline.
 *
 * react-markdown marks the difference with a `language-*` class and the newline
 * the fence leaves behind, so a single-word fence is still treated as a block. Both are
 * read: a fence with no language has no class, and an inline span never holds a newline
 * (the parser turns one into a space).
 */
const components: Components = {
  a: SafeLink,
  img: ({ src, alt, title }) => <MarkdownImage src={typeof src === "string" ? src : undefined} alt={alt} title={title} />,
  code({ className, children, ...props }) {
    const text = plainText(children);
    const fenced =
      (typeof className === "string" && className.startsWith("language-")) || text.includes("\n");
    if (!fenced) {
      return (
        <code className="md-inline" {...props}>
          {children}
        </code>
      );
    }
    // The fence leaves a trailing newline that nobody selecting the block by hand would take.
    const code = text.replace(/\n$/, "");
    return (
      <div className="md-code">
        <pre className="md-pre">
          <code className={className} {...props}>
            {children}
          </code>
        </pre>
        <CopyButton text={code} label={vi.copy.code} />
      </div>
    );
  },
  // The default wraps a fenced block in another <pre>; the code renderer above
  // already made one, so this keeps the markup from nesting twice.
  pre({ children }) {
    return <>{children}</>;
  },
};

const wikiPlugins = [remarkGfm, remarkWikiLinks];

interface Props {
  text: string;
  /**
   * Given only for a wiki page: `[[Name]]` then becomes a link, and this draws it. The
   * link must stay inside the app (open the page in place), so it never reaches SafeLink.
   */
  wikiLink?: (slug: string, label: ReactNode) => ReactNode;
  /** Writes characters that change how text reads without being seen as marks, for a canvas,
   *  which may hold text an agent copied from a web page. */
  showHidden?: boolean;
}

export function MarkdownBody({ text, wikiLink, showHidden = false }: Props) {
  const withWiki = useMemo<Components | null>(
    () =>
      wikiLink
        ? {
            ...components,
            a({ href, children }) {
              const slug = wikiSlugFromHref(href);
              return slug === null ? <SafeLink href={href}>{children}</SafeLink> : wikiLink(slug, children);
            },
          }
        : null,
    [wikiLink],
  );
  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={[...(withWiki ? wikiPlugins : [remarkGfm]), ...(showHidden ? [remarkHiddenChars] : [])]}
        components={withWiki ?? components}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
