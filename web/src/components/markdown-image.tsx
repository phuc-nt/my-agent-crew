import { useEffect, useRef, useState } from "react";
import { vi } from "../i18n/vi";

/** The host an image would be fetched from, or null when fetching it tells no one else:
 *  the app's own server. (react-markdown has already dropped a URL of any other scheme.) */
export function remoteHost(src: string): string | null {
  let url: URL;
  try {
    url = new URL(src, window.location.href);
  } catch {
    return null;
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") return null;
  return url.origin === window.location.origin ? null : url.host;
}

/**
 * An image in a reply or a wiki page. One served from elsewhere waits for a tap: a reply
 * is partly built from fetched pages and tool output, and an image loaded on sight would
 * tell whoever serves it — a tracking pixel's owner — that this was read, when and from
 * where. The app's own images load as usual. Once asked for, the image
 * loads without a referrer, and takes the focus its button held.
 *
 * The yes is to the address the button showed, and what is kept is that address: a page drawn
 * again with another image in this place, as one being written or edited is, asks again. The
 * button that comes back takes the keyboard only when the image it replaces held it; left alone,
 * the focus would fall to the page.
 */
export function MarkdownImage({ src, alt, title }: { src?: string; alt?: string; title?: string }) {
  const [asked, setAsked] = useState<string | null>(null);
  const image = useRef<HTMLImageElement>(null);
  const hold = useRef<HTMLButtonElement>(null);
  // Whether the keyboard is on the image. An element taken off the page is sent no blur, so this
  // still says yes in the effect that runs once the button stands in its place.
  const onImage = useRef(false);
  const host = src ? remoteHost(src) : null;
  const held = host !== null && asked !== src;
  useEffect(() => {
    if (asked) image.current?.focus();
  }, [asked]);
  useEffect(() => {
    if (!held) return;
    if (onImage.current) hold.current?.focus();
    onImage.current = false;
  }, [held]);
  if (!src) return null;
  if (host !== null && held) {
    return (
      <button ref={hold} type="button" className="md-image-hold" title={src} onClick={() => setAsked(src)}>
        {vi.markdownImage.show(host)}
        {alt && " "}
        {alt && <span className="md-image-alt">{alt}</span>}
      </button>
    );
  }
  return (
    <img
      ref={image}
      src={src}
      alt={alt ?? ""}
      title={title}
      loading="lazy"
      referrerPolicy="no-referrer"
      tabIndex={host ? -1 : undefined}
      onFocus={() => {
        onImage.current = true;
      }}
      onBlur={() => {
        onImage.current = false;
      }}
    />
  );
}
