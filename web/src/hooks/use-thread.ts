import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import type { MessageCanvas } from "../api/artifact-types";
import { api, ApiError } from "../api/client";
import type { AgentEvent, ConversationDetail, StopResult } from "../api/types";
import { turnErrorText } from "../lib/error-text";
import type { SendResult } from "../lib/send-result";
import { endsTurn } from "../lib/turn-end";
import { emptyThread, threadReducer, type ThreadState } from "../state/thread-reducer";
import { useThreadSend } from "./use-thread-send";

/** How long Stop waits on the server before giving up and cutting the stream locally
 *  anyway. A `setTimeout` rather than `AbortSignal.timeout`, so a test can drive it with
 *  fake timers instead of waiting out a real three seconds. */
const STOP_WAIT_MS = 3000;

export interface ThreadController {
  state: ThreadState;
  detail: ConversationDetail | null;
  /** Sends `text` and says how that went the moment the server says anything — see
   *  `SendResult` — while the turn it starts goes on after that. Found busy, this tab's own
   *  stream or one this tab did not start, the message queues instead. `canvas` is the one
   *  open in this tab, which the server takes as the conversation's; left out, it keeps its own. */
  send: (text: string, canvas?: MessageCanvas) => Promise<SendResult>;
  /** `always` also whitelists the tool for the rest of this conversation. */
  decide: (approve: boolean, always?: boolean) => Promise<void>;
  /** Reply to a question the agent asked. Only a question row accepts this. */
  answer: (text: string) => Promise<void>;
  /** Tells the server to end the turn and hand back every message still queued, then cuts
   *  this tab's stream of a turn that was ended; resolves with the cleared texts, oldest
   *  first, so the caller can put them back in the composer. `externalRunning` says whether a
   *  turn is known to be going somewhere this tab cannot reach, for the notice it may show. */
  stop: (externalRunning?: boolean) => Promise<string[]>;
  /** Reads along with the turn under way here, whoever started it, unless this tab is
   *  reading one already. Resolves once it has no more to read, false when there was nothing:
   *  the server had no turn under way, or could not be asked. */
  watch: () => Promise<boolean>;
  /** The turn on screen is one this tab reads along with, not one it started. */
  watching: boolean;
  reload: () => Promise<void>;
  /** Loads again now, or once this tab's turn is over: a load mid-turn would drop it. */
  reloadWhenIdle: () => void;
  /** Marks calls no run will answer any more as stopped; a no-op while a turn runs. */
  settle: () => void;
  /** The person put away a canvas being written: none comes up by itself for the rest of the turn. */
  mutePreviews: () => void;
  /** Counts the times a run turned out not to be read by a stream this tab started: a
   *  decision refused as already taken elsewhere, a turn joined by watching, a stream lost
   *  while its turn went on, a stream that closed before its turn's last word. Whatever run
   *  was put down to this tab then is not its own. */
  unowned: number;
  /** Counts the Stops the server answered by ending the turn. The run going here then is
   *  over, though the activity stream says so only once the turn has let go of its work. */
  stops: number;
}

/** Owns one conversation: loads its history, streams turns, resolves approvals. */
export function useThread(conversationId: string | null): ThreadController {
  const [state, dispatch] = useReducer(threadReducer, emptyThread);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  // The stream in `abortRef` when it is a watch: a turn this tab reads but did not start.
  const watchRef = useRef<AbortController | null>(null);
  const [watching, setWatching] = useState(false);
  const turns = useRef(0);
  // Controllers for a queueing POST still in flight: a busy-send never touches `abortRef`,
  // since that would cut the turn actually running rather than the message trying to join
  // its queue. Switching conversation or unmounting cuts every one of these instead.
  const queueingRef = useRef(new Set<AbortController>());
  // Set for the run of a Stop call and cleared once it settles, so a second press while one
  // is still in flight can tell and skip the server call rather than sending it twice.
  const stoppingRef = useRef(false);
  const [owed, setOwed] = useState(false);
  const [unowned, setUnowned] = useState(0);
  const [stops, setStops] = useState(0);
  // A fresh object each time a conversation is opened: whatever answers for an opening
  // that is no longer the one on screen belongs to a thread the person has left.
  const opened = useRef<{ id: string | null }>({ id: null });

  const reload = useCallback(async () => {
    if (!conversationId) {
      setDetail(null);
      return;
    }
    const opening = opened.current;
    if (opening.id !== conversationId) return;
    // A turn begun while the load was on its way has put the person's message and its
    // stream on screen, which this older copy lacks: it loads again once the turn is over.
    const turn = turns.current;
    try {
      const loaded = await api.getConversation(conversationId);
      if (opening !== opened.current) return;
      if (turn !== turns.current) return setOwed(true);
      setDetail(loaded);
      dispatch({ type: "loaded", detail: loaded });
    } catch (error) {
      if (opening !== opened.current) return;
      if (turn !== turns.current) return setOwed(true);
      dispatch({ type: "failed", message: turnErrorText(error) });
    }
  }, [conversationId]);

  useEffect(() => {
    opened.current = { id: conversationId };
    abortRef.current?.abort();
    for (const controller of queueingRef.current) controller.abort();
    queueingRef.current.clear();
    setOwed(false);
    setWatching(false);
    dispatch({ type: "opened" });
    void reload();
  }, [conversationId, reload]);

  useEffect(() => {
    if (!owed || state.busy) return;
    setOwed(false);
    void reload();
  }, [owed, state.busy, reload]);
  const reloadWhenIdle = useCallback(() => setOwed(true), []);

  const onEvent = useCallback((event: AgentEvent) => {
    if (event.type === "watching") {
      // The server hands over the conversation as it is stored now: a load still on its
      // way is older than that, and loads again once the turn is over.
      turns.current += 1;
      setDetail(event.detail);
    }
    dispatch({ type: "event", event });
  }, []);

  /** Runs a turn on a stream this tab starts. `turnless` is asked once the stream has closed,
   *  and says the server answered with no turn on it: the message was only put in line, or
   *  the decision was refused. */
  const runTurn = useCallback(
    async (
      run: (onEvent: (e: AgentEvent) => void, signal: AbortSignal) => Promise<void>,
      describe: (error: unknown) => string = turnErrorText,
      turnless: () => boolean = () => false,
    ) => {
      const controller = new AbortController();
      watchRef.current?.abort(); // one stream feeds the thread: this one takes over
      abortRef.current = controller;
      turns.current += 1;
      dispatch({ type: "turn_started" });
      const said = { last: false };
      // An aborted stream is one this tab stopped reading — Stop, or another conversation
      // opened — so nothing it still delivers may land in the thread on screen. The turn
      // itself is the server's: only Stop ends it.
      const emit = (event: AgentEvent) => {
        if (controller.signal.aborted) return;
        said.last ||= endsTurn(event);
        onEvent(event);
      };
      try {
        await run(emit, controller.signal);
        if (controller.signal.aborted) return;
        dispatch({ type: "turn_finished" });
        // A stream that closed before its turn's last word says nothing of the turn: a
        // server told to go ends its streams so and the next one carries the turn on, or
        // the turn was stopped elsewhere. Its run is this tab's no more, so the server is
        // asked about it, as it is of any run this tab does not read.
        if (!said.last && !turnless()) setUnowned((n) => n + 1);
      } catch (error) {
        if (controller.signal.aborted) return;
        dispatch({ type: "failed", message: describe(error) });
        // What failed is this tab's reading. A turn the server did start goes on without it.
        setUnowned((n) => n + 1);
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
      }
    },
    [onEvent],
  );

  /** Carries out a decision. A 409 means someone got there first — another tab, Telegram
   *  or the expiry sweep — which is not the conversation being busy: saying so would send
   *  the person to wait for something already over. The thread is read again to show how
   *  far it has got, which also covers any load owed, and then says the request was
   *  handled; a run resumed elsewhere may still be going, so nothing is settled. */
  const decisionTurn = useCallback(
    async (run: (onEvent: (e: AgentEvent) => void, signal: AbortSignal) => Promise<void>) => {
      const opening = opened.current;
      let handled = false;
      await runTurn(
        async (emit, signal) => {
          try {
            await run(emit, signal);
          } catch (error) {
            if (!(error instanceof ApiError && error.status === 409)) throw error;
            if (opening !== opened.current) return;
            handled = true;
            setOwed(false);
            setUnowned((n) => n + 1);
          }
        },
        undefined,
        // The refusal is counted above, where a Stop pressed meanwhile cannot leave it out.
        () => handled,
      );
      if (!handled) return;
      await reload();
      if (opening === opened.current) dispatch({ type: "handled" });
    },
    [runTurn, reload],
  );

  const send = useThreadSend({ conversationId, busy: state.busy, dispatch, runTurn, queueing: queueingRef });

  const decide = useCallback(
    async (approve: boolean, always = false) => {
      const pending = state.pending;
      if (!conversationId || !pending) return;
      await decisionTurn((emit, signal) =>
        api.resolveApproval(conversationId, pending.approvalId, approve, emit, always && approve, signal),
      );
    },
    [conversationId, decisionTurn, state.pending],
  );

  const answer = useCallback(
    async (text: string) => {
      const pending = state.pending;
      if (!conversationId || !pending || pending.kind !== "question") return;
      await decisionTurn((emit, signal) =>
        api.answerApproval(conversationId, pending.approvalId, text, emit, signal),
      );
    },
    [conversationId, decisionTurn, state.pending],
  );

  const watch = useCallback(async () => {
    if (!conversationId) return false;
    if (abortRef.current && !abortRef.current.signal.aborted) return true;
    const controller = new AbortController();
    abortRef.current = watchRef.current = controller;
    let attached = false;
    try {
      const found = await api.watchTurn(
        conversationId,
        (event) => {
          if (controller.signal.aborted) return;
          if (event.type === "watching" && !attached) {
            attached = true;
            setWatching(true);
            setUnowned((n) => n + 1);
          }
          onEvent(event);
        },
        controller.signal,
      );
      return found || controller.signal.aborted;
    } catch {
      // The view of the turn was lost, not the turn: nothing here to tell the person.
      return attached || controller.signal.aborted;
    } finally {
      // However the stream ended, nothing more of the turn reaches this tab through it. One
      // ended without a last event was stopped elsewhere, or lost: its calls stop spinning.
      if (attached && !controller.signal.aborted) dispatch({ type: "turn_finished" });
      if (abortRef.current === controller) abortRef.current = null;
      if (watchRef.current === controller) {
        watchRef.current = null;
        setWatching(false);
      }
    }
  }, [conversationId, onEvent]);

  /**
   * Stop. The server is told first — it alone knows the queue and whether the turn is its
   * to end — and only then is this tab's stream cut, so a fast reply never races the abort
   * into unwinding before `queue_cleared` and `turn_stopped`/`elsewhere` are both decided
   * from the same server answer.
   *
   * A turn this tab only watches is cut when the server ended it. One the server could not
   * end — a bot's, a job's — goes on, and so does the watching, under a note saying so.
   *
   * A server that errors or does not answer within `STOP_WAIT_MS` still leaves the local
   * stream cut: the person asked to stop, and a slow or unreachable server is not a reason to
   * keep this tab's view of the turn running. The run is no longer put down to this tab, so
   * a turn found still going is watched again. The chips stay in that case — they are still
   * sitting on the server, unconfirmed — so pressing Stop again is exactly the right next
   * move, and `waiting.length > 0` is what keeps the button around for it.
   */
  const stop = useCallback(
    async (externalRunning = false) => {
      if (stoppingRef.current) return [];
      stoppingRef.current = true;
      try {
        if (!conversationId) return [];
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), STOP_WAIT_MS);
        let result: StopResult | null = null;
        try {
          result = await api.stopConversation(conversationId, controller.signal);
        } catch {
          result = null;
        } finally {
          clearTimeout(timer);
        }
        const reading = abortRef.current?.signal.aborted ? null : abortRef.current;
        const watched = reading !== null && reading === watchRef.current;
        if (result) {
          dispatch({ type: "queue_cleared" });
          if (result.cancelled || (reading !== null && !watched)) {
            reading?.abort();
            dispatch({ type: "turn_stopped" });
            if (result.cancelled) setStops((n) => n + 1);
          } else if (watched || externalRunning) dispatch({ type: "elsewhere" });
          return result.cleared.map((c) => c.text);
        }
        reading?.abort();
        if (reading !== null) {
          dispatch({ type: "turn_stopped" });
          setUnowned((n) => n + 1);
        }
        return [];
      } finally {
        stoppingRef.current = false;
      }
    },
    [conversationId],
  );

  const settle = useCallback(() => dispatch({ type: "settled" }), []);
  const mutePreviews = useCallback(() => dispatch({ type: "previews_muted" }), []);

  return {
    state,
    detail,
    send,
    decide,
    answer,
    stop,
    watch,
    watching,
    reload,
    reloadWhenIdle,
    settle,
    mutePreviews,
    unowned,
    stops,
  };
}
