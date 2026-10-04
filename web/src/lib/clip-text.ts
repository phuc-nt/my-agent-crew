/**
 * `text` cut to at most `max` UTF-16 units. A cut between the two halves of a surrogate pair would
 * leave a lone half that no font draws, so the pair goes whole.
 */
export function clip(text: string, max: number): string {
  if (text.length <= max) return text;
  const last = text.charCodeAt(max - 1);
  return text.slice(0, last >= 0xd800 && last <= 0xdbff ? max - 1 : max);
}
