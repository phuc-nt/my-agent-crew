/**
 * The history of one canvas: its versions, the newest first, the version picked and the one it is
 * compared with, the texts read so far, and the restore. A version's text is read once, when it is
 * picked or compared with. A version folded away since the list was read makes the list read
 * again; a canvas the server no longer has is announced as deleted, as the stream would have.
 *
 * Version numbers have gaps, so "the version before" is the one listed after it, never `n - 1`.
 * A restore saves the typing first: a version restored over unsaved text would drop it.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { artifactApi, storageFullOf, versionGoneOf } from "../api/artifact-client";
import type { ArtifactVersionMeta, StorageFull } from "../api/artifact-types";
import { ApiError } from "../api/client";
import { announceDeletion } from "../lib/artifact-events";
import { canvasReason } from "../lib/canvas-reasons";

/** What went wrong last; a newer problem replaces it, and a pick or a restore clears it. */
export type HistoryProblem =
  | { type: "versionGone" }
  | { type: "versionFailed" }
  /** The typing could not be saved, so nothing was restored over it. */
  | { type: "blocked" }
  | { type: "full"; full: StorageFull }
  | { type: "restoreFailed"; reason: string };

export type CanvasHistory = {
  /** Newest first; null until the first read lands. */
  versions: ArtifactVersionMeta[] | null;
  listFailed: boolean;
  shown: ArtifactVersionMeta | null;
  /** What `shown` is compared with: the version listed after it, or the oldest kept on request;
   *  null when `shown` is the oldest. */
  against: ArtifactVersionMeta | null;
  compareFirst: boolean;
  texts: ReadonlyMap<number, string>;
  problem: HistoryProblem | null;
  restoring: boolean;
  pick(version: number): void;
  setCompareFirst(on: boolean): void;
  retry(): void;
  restore(): Promise<void>;
};

type Options = {
  artifactId: string;
  /** The newest version the panel knows of: the list is read again when it moves. */
  headVersion: number | undefined;
  /** Saves the typing; the version that holds it, or null when none will. */
  flush(): Promise<number | null>;
  /** Version `version`, holding `content`, is now the newest. */
  onRestored(version: number, content: string): void;
};

/** A 404 for the canvas itself, not for one of its versions. */
const canvasGone = (error: unknown) =>
  error instanceof ApiError && error.status === 404 && versionGoneOf(error) === null;

export function useCanvasHistory({ artifactId, headVersion, flush, onRestored }: Options): CanvasHistory {
  const [versions, setVersions] = useState<ArtifactVersionMeta[] | null>(null);
  const [listFailed, setListFailed] = useState(false);
  const [reads, setReads] = useState(0);
  const [picked, setPicked] = useState<number | null>(null);
  // Every pick, so picking a version whose read failed reads it again.
  const [picks, setPicks] = useState(0);
  const [compareFirst, setCompareFirst] = useState(false);
  const [texts, setTexts] = useState<ReadonlyMap<number, string>>(() => new Map());
  const [problem, setProblem] = useState<HistoryProblem | null>(null);
  const [restoring, setRestoring] = useState(false);
  // Versions read or being read, so an effect run twice asks once.
  const asked = useRef(new Set<number>());
  const reload = useCallback(() => setReads((count) => count + 1), []);

  useEffect(() => {
    let live = true;
    setListFailed(false);
    artifactApi.versions(artifactId).then(
      (found) => {
        if (live) setVersions([...found].sort((a, b) => b.version - a.version));
      },
      (error: unknown) => {
        if (!live) return;
        if (canvasGone(error)) announceDeletion(artifactId);
        else setListFailed(true);
      },
    );
    return () => {
      live = false;
    };
  }, [artifactId, headVersion, reads]);

  // The version picked while it is listed, else the newest.
  const list = versions ?? [];
  const at = Math.max(0, list.findIndex((meta) => meta.version === picked));
  const shown = list[at] ?? null;
  const oldest = list.at(-1) ?? null;
  const against = shown === null || shown === oldest ? null : compareFirst ? oldest : (list[at + 1] ?? null);

  const shownVersion = shown?.version ?? null;
  const againstVersion = against?.version ?? null;
  useEffect(() => {
    for (const version of [shownVersion, againstVersion]) {
      if (version === null || asked.current.has(version)) continue;
      asked.current.add(version);
      artifactApi.version(artifactId, version).then(
        (found) => setTexts((known) => new Map(known).set(version, found.content)),
        (error: unknown) => {
          asked.current.delete(version);
          if (versionGoneOf(error) !== null) {
            setProblem({ type: "versionGone" });
            reload();
          } else if (canvasGone(error)) announceDeletion(artifactId);
          else setProblem({ type: "versionFailed" });
        },
      );
    }
  }, [artifactId, shownVersion, againstVersion, picks, reload]);

  const restore = async () => {
    const content = shown ? texts.get(shown.version) : undefined;
    if (!shown || content === undefined) return;
    setRestoring(true);
    setProblem(null);
    try {
      if ((await flush()) === null) {
        setProblem({ type: "blocked" });
        return;
      }
      const meta = await artifactApi.restore(artifactId, shown.version);
      onRestored(meta.version, content);
    } catch (error) {
      const full = storageFullOf(error);
      if (versionGoneOf(error) !== null) {
        setProblem({ type: "versionGone" });
        reload();
      } else if (canvasGone(error)) announceDeletion(artifactId);
      else setProblem(full ? { type: "full", full } : { type: "restoreFailed", reason: canvasReason(error) });
    } finally {
      setRestoring(false);
    }
  };

  const pick = (version: number) => {
    setPicked(version);
    setPicks((count) => count + 1);
    setProblem(null);
  };

  return {
    versions,
    listFailed,
    shown,
    against,
    compareFirst,
    texts,
    problem,
    restoring,
    pick,
    setCompareFirst,
    retry: reload,
    restore,
  };
}
