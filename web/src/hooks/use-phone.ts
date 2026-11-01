import { useMediaQuery } from "./use-media-query";

/** A phone: the list becomes a drawer and the chat folds what can wait. Matches the
 *  breakpoint in shell-responsive.css. */
export const PHONE_QUERY = "(max-width: 720px)";

export function usePhone(): boolean {
  return useMediaQuery(PHONE_QUERY);
}
