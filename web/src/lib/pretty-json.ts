/**
 * JSON text set out one member to a line, or null when the text is not JSON.
 *
 * The text is re-spaced, never re-written: each string and number is copied as it stands.
 * Parsing and printing again would round a number wider than a double holds, and a value
 * a script kept has to read here as the value it will load.
 */
export function prettyJson(text: string): string | null {
  try {
    JSON.parse(text);
  } catch {
    return null;
  }
  const out: string[] = [];
  let depth = 0;
  const line = () => out.push(`\n${"  ".repeat(depth)}`);
  for (let at = 0; at < text.length; at += 1) {
    const char = text[at];
    if (char === '"') {
      const end = stringEnd(text, at);
      out.push(text.slice(at, end + 1));
      at = end;
    } else if (char === "{" || char === "[") {
      const next = skipSpace(text, at + 1);
      // An empty one stays on its line: nothing in it is worth two more.
      if (text[next] === "}" || text[next] === "]") {
        out.push(char, text[next]);
        at = next;
      } else {
        out.push(char);
        depth += 1;
        line();
      }
    } else if (char === "}" || char === "]") {
      depth -= 1;
      line();
      out.push(char);
    } else if (char === ",") {
      out.push(char);
      line();
    } else if (char === ":") {
      out.push(": ");
    } else if (!isSpace(char)) {
      out.push(char);
    }
  }
  return out.join("");
}

const isSpace = (char: string) => char === " " || char === "\n" || char === "\t" || char === "\r";

function skipSpace(text: string, from: number): number {
  let at = from;
  while (at < text.length && isSpace(text[at])) at += 1;
  return at;
}

/** Where the string that opens at `from` closes. The text is known to be JSON, so it does. */
function stringEnd(text: string, from: number): number {
  let at = from + 1;
  while (text[at] !== '"') at += text[at] === "\\" ? 2 : 1;
  return at;
}
