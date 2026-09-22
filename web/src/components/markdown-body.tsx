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
 * thread.
 */

import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

/** Links leave the app, so they open away from the conversation and cannot reach it. */
function SafeLink({ href, children }: { href?: string; children?: React.ReactNode }) {
  if (!href) return <span>{children}</span>;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  );
}

/**
 * Fenced blocks get a scrollable `<pre>`; an inline span stays inline.
 *
 * react-markdown marks the difference with a `language-*` class and the newline
 * the fence leaves behind, so a single-word fence is still treated as a block.
 */
const components: Components = {
  a: SafeLink,
  code({ className, children, ...props }) {
    const fenced = typeof className === "string" && className.startsWith("language-");
    if (!fenced) {
      return (
        <code className="md-inline" {...props}>
          {children}
        </code>
      );
    }
    return (
      <pre className="md-pre">
        <code className={className} {...props}>
          {children}
        </code>
      </pre>
    );
  },
  // The default wraps a fenced block in another <pre>; the code renderer above
  // already made one, so this keeps the markup from nesting twice.
  pre({ children }) {
    return <>{children}</>;
  },
};

export function MarkdownBody({ text }: { text: string }) {
  return (
    <div className="md">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {text}
      </ReactMarkdown>
    </div>
  );
}
