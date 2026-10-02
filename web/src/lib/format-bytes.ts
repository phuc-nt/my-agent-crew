const UNITS = ["KB", "MB", "GB", "TB"] as const;

/**
 * A size as people read it: "812 B", "432 KB", "1,2 MB". Built by hand, since Intl's vi-VN
 * output differs between the ICU builds of Node and the browsers (see relative-time.ts).
 */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  let value = bytes / 1024;
  let unit = 0;
  // 1023.6 KB would print as "1024 KB"; it reads better as the next unit.
  while (Math.round(value) >= 1024 && unit < UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${amount(value)} ${UNITS[unit]}`;
}

/** One decimal under ten, after a comma and left out when it is zero; whole numbers above. */
function amount(value: number): string {
  const tenths = Math.round(value * 10);
  if (tenths < 100) return tenths % 10 === 0 ? String(tenths / 10) : `${Math.floor(tenths / 10)},${tenths % 10}`;
  return String(Math.round(value));
}
