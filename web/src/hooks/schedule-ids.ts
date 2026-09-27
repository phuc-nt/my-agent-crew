// Which id each schedule row is saved under, and which typed ids cannot be saved.
//
// The server numbers a row sent without an id by its place, `job-{index}`, and the scheduler
// keys its jobs by id. Remove the first of two rows and add one: the kept row still carries
// `job-1` and the new row sits at index 1, so both would be `job-1` and one job would
// quietly replace the other. The server refuses that save, so the form never sends it: a
// blank id that would land on a taken one is given the first free `job-N` instead.

/** The id the memory consolidation job runs under while `memory_consolidate` is set. */
export const CONSOLIDATE_ID = "memory-consolidate";

type Row = { id: string };

const typed = (row: Row) => row.id.trim() !== "";

/**
 * The id to send for each row: a typed id as typed, `""` where the server's own numbering
 * is already free, and a free `job-N` where it is not. Only a blank id is ever filled in —
 * renaming a typed one would split the job's run history from its new name.
 */
export function idsToSend(rows: readonly Row[]): string[] {
  const taken = new Set(rows.filter(typed).map((row) => row.id));
  return rows.map((row, at) => {
    if (typed(row)) return row.id;
    let number = at;
    while (taken.has(`job-${number}`)) number += 1;
    taken.add(`job-${number}`);
    return number === at ? "" : `job-${number}`;
  });
}

/** Indexes of rows whose typed id the server would refuse: one already used by an earlier
 * row, or the consolidation job's while that job is on. */
export function clashingIds(rows: readonly Row[], consolidating: boolean): Map<number, "taken" | "reserved"> {
  const clashes = new Map<number, "taken" | "reserved">();
  const seen = new Set<string>();
  rows.forEach((row, at) => {
    if (!typed(row)) return;
    if (consolidating && row.id === CONSOLIDATE_ID) clashes.set(at, "reserved");
    else if (seen.has(row.id)) clashes.set(at, "taken");
    seen.add(row.id);
  });
  return clashes;
}
