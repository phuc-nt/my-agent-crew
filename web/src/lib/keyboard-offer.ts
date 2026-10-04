/**
 * The offer of the keyboard a person makes to the page in a frame. It is made to one frame, the
 * one on show then, and for the focus that moves with what made it: a frame that does not have the
 * focus once that had its time has no offer left to take the keyboard by later.
 */

export type KeyboardOffer = {
  /** Offers the keyboard to `frame`, which has `within` ms to be found with the focus. */
  make(frame: HTMLIFrameElement | null, within: number): void;
  withdraw(): void;
  /** Whether the offer that stands was made to `frame`. */
  madeTo(frame: HTMLIFrameElement): boolean;
};

export function keyboardOffer(): KeyboardOffer {
  let to: HTMLIFrameElement | null = null;
  let over: ReturnType<typeof setTimeout> | undefined;
  const withdraw = () => {
    to = null;
    clearTimeout(over);
  };
  const make = (frame: HTMLIFrameElement | null, within: number) => {
    withdraw();
    to = frame;
    over = setTimeout(() => {
      if (document.activeElement !== frame) withdraw();
    }, within);
  };
  return { make, withdraw, madeTo: (frame) => to === frame };
}
