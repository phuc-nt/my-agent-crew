import type { MessageCanvas } from "../artifact-types";
import type {
  AgentEvent,
  ApprovalInfo,
  Conversation,
  ConversationDetail,
  ConversationPatch,
  ForkResult,
  StopResult,
} from "../types";
import { follow, query, request, stream } from "./http";

export const conversationsApi = {
  listConversations: (agentId?: string) =>
    request<Conversation[]>(`/conversations${query({ agent_id: agentId })}`),
  createConversation: (body: ConversationPatch & { agent_id?: string } = {}) =>
    request<Conversation>("/conversations", { method: "POST", body: JSON.stringify(body) }),
  getConversation: (id: string) => request<ConversationDetail>(`/conversations/${id}`),
  patchConversation: (id: string, body: ConversationPatch) =>
    request<Conversation>(`/conversations/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteConversation: (id: string) =>
    request<void>(`/conversations/${id}`, { method: "DELETE" }),
  /** Rewind and fork: a new conversation holding every message before `beforeMessageId`,
   *  with that message's own text handed back as a draft. */
  forkConversation: (id: string, beforeMessageId: number) =>
    request<ForkResult>(`/conversations/${id}/fork`, {
      method: "POST",
      body: JSON.stringify({ before_message_id: beforeMessageId }),
    }),
  summarizeConversation: (id: string) =>
    request<{ id: string; summary: string }>(`/conversations/${id}/summary`, { method: "POST" }),
  /** `canvas` is the canvas open in this tab. Left out, the server keeps the one it has
   *  (a tab that does not know yet must not close what another opened); `{artifact_id: null}`
   *  says none is open. */
  sendMessage: (
    id: string,
    text: string,
    onEvent: (e: AgentEvent) => void,
    signal?: AbortSignal,
    canvas?: MessageCanvas,
    requestId?: string,
  ) =>
    stream(
      `/conversations/${id}/messages`,
      { text, ...(canvas === undefined ? {} : { canvas }), ...(requestId ? { request_id: requestId } : {}) },
      onEvent,
      signal,
    ),
  /** Reads along with the turn under way in a conversation, whoever started it: first a
   *  `watching` event to rebuild the thread from, then the turn's own events to its end.
   *  Resolves false at once when no turn is under way. */
  watchTurn: (id: string, onEvent: (e: AgentEvent) => void, signal?: AbortSignal) =>
    follow(`/conversations/${id}/turn`, { signal }, onEvent),
  /** Takes every message still waiting for this conversation's turn back out of the queue,
   *  and stops the turn too where the server can reach it — see `StopResult`. */
  stopConversation: (id: string, signal?: AbortSignal) =>
    request<StopResult>(`/conversations/${id}/stop`, { method: "POST", signal }),
  resolveApproval: (
    id: string,
    approvalId: string,
    approve: boolean,
    onEvent: (e: AgentEvent) => void,
    always = false,
    signal?: AbortSignal,
  ) =>
    stream(
      `/conversations/${id}/approvals/${approvalId}`,
      always ? { approve, always: true } : { approve },
      onEvent,
      signal,
    ),
  /** A question closes by its own route. The approve/deny route refuses a question row,
   *  so answering through it would leave the agent waiting until the deadline. */
  answerApproval: (
    id: string,
    approvalId: string,
    answer: string,
    onEvent: (e: AgentEvent) => void,
    signal?: AbortSignal,
  ) => stream(`/conversations/${id}/approvals/${approvalId}/answer`, { answer }, onEvent, signal),
  listApprovals: (params: { limit?: number; conversation_id?: string } = {}) =>
    request<ApprovalInfo[]>(`/approvals${query(params)}`),
};
