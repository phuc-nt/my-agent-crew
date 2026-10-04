/**
 * What each kind of canvas is shown as. A kind the web does not know shows as text, like code.
 * The server decides what a kind can do; these only say how the panel draws it.
 */

/** A page the server can run in a sandbox: an HTML canvas, or a Mermaid diagram it wraps in one. */
export const showsPage = (kind: string): boolean => kind === "html" || kind === "mermaid";

/** A picture: a drawing the browser sets as an image, or an image that came in as bytes. */
export const showsPicture = (kind: string): boolean => kind === "svg" || kind === "image";

/**
 * Whether View shows what the server holds rather than the text on the screen. The text a person
 * has typed and not yet saved is not in it, so turning to View waits for the save and says so when
 * some text is still not in the version shown.
 */
export const showsSaved = (kind: string): boolean => showsPage(kind) || showsPicture(kind);

/** A canvas with no text of its own: nothing to edit, copy or select a passage of. */
export const hasNoText = (kind: string): boolean => kind === "image";
