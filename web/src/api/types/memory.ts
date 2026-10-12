/** One remembered fact about the person, shared by every agent. */
export interface FactInfo {
  name: string;
  description: string;
  type: FactType;
  written_by: string;
  source: string;
  updated: string;
  body: string;
  /** Server-computed: `updated` is more than ninety days old. */
  stale: boolean;
}

export type FactType = "profile" | "preference" | "feedback" | "project" | "reference";

export const FACT_TYPES: FactType[] = [
  "profile",
  "preference",
  "feedback",
  "project",
  "reference",
];

export interface UserMemory {
  user_md: string;
  facts: FactInfo[];
  index_md: string;
}

/** A dated note beside one agent's MEMORY.md; the body is fetched on demand. */
export interface MemoryNote {
  /** The file name without `.md`: a date, sometimes with a suffix (`2026-09-19-1030`). */
  day: string;
  chars: number;
  /** The calendar day alone, shared by every note written that day. */
  date: string;
}

export interface AgentMemory {
  memory_md: string;
  notes: MemoryNote[];
  note_count: number;
}

export interface MemoryHit {
  scope: "user" | "agent";
  /** "" for a shared fact, else the agent whose file matched. */
  agent_id: string;
  file: string;
  text: string;
}

/** One matched message from `GET /api/messages/search`, across past conversations. */
export interface ContentHit {
  conversation_id: string;
  agent_id: string;
  title: string;
  message_id: string;
  role: string;
  snippet: string;
  created_at: string;
}

export type ProposalKind =
  | "user_fact"
  | "user_forget"
  | "agent_memory"
  | "agent_memory_rewrite"
  /** A whole batch of wiki pages, decided in one approval; the body is JSON. */
  | "wiki_compile";
/** "superseded" is a proposal a newer one of the same kind made obsolete, or one whose
 *  file changed under it before anyone decided — distinct from "rejected": nobody said
 *  no, the ground moved. */
export type ProposalStatus = "pending" | "approved" | "rejected" | "superseded";

/** A memory write a scheduled job asked for and cannot perform on its own. */
export interface MemoryProposal {
  id: string;
  agent_id: string;
  kind: ProposalKind;
  name: string;
  description: string;
  type: string;
  body: string;
  /** What a rewrite replaces, kept so one step back is always possible. */
  previous_body: string;
  status: ProposalStatus;
  source: string;
  /** Why the model changed or dropped each line, one bullet per decision. Empty when the
   *  proposal is a plain addition with nothing to explain. */
  reasons: string;
  created_at: string;
  resolved_at: string | null;
}

export interface FactBody {
  description: string;
  type: FactType;
  body: string;
}
