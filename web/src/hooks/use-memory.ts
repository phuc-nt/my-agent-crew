import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type {
  AgentMemory,
  FactBody,
  MemoryHit,
  MemoryProposal,
  UserMemory,
} from "../api/types";

export interface MemoryController {
  user: UserMemory | null;
  agentMemory: AgentMemory | null;
  proposals: MemoryProposal[];
  hits: MemoryHit[] | null;
  loadedAt: string;
  saveUserMd: (text: string) => Promise<void>;
  saveFact: (name: string, body: FactBody) => Promise<void>;
  removeFact: (name: string) => Promise<void>;
  saveAgentMemory: (text: string) => Promise<void>;
  readNote: (day: string) => Promise<string>;
  saveNote: (day: string, body: string) => Promise<void>;
  search: (query: string, onlyThisAgent: boolean) => Promise<void>;
  decide: (id: string, approve: boolean) => Promise<void>;
  consolidate: () => Promise<void>;
  undo: (proposal: MemoryProposal) => Promise<void>;
}

/**
 * Everything the memory panel reads and writes for one selected agent.
 *
 * `pendingCount` comes from the stats the rail already polls, so a proposal left by a
 * job that just finished pulls the list again without the panel polling on its own.
 */
export function useMemory(agentId: string, pendingCount: number): MemoryController {
  const [user, setUser] = useState<UserMemory | null>(null);
  const [agentMemory, setAgentMemory] = useState<AgentMemory | null>(null);
  const [proposals, setProposals] = useState<MemoryProposal[]>([]);
  const [hits, setHits] = useState<MemoryHit[] | null>(null);
  const [loadedAt, setLoadedAt] = useState("");

  const stamp = () => setLoadedAt(new Date().toLocaleTimeString("vi-VN"));

  useEffect(() => {
    api.getUserMemory().then((next) => {
      setUser(next);
      stamp();
    }, () => setUser(null));
  }, []);

  useEffect(() => {
    if (!agentId) return;
    api.getAgentMemory(agentId).then(setAgentMemory, () => setAgentMemory(null));
  }, [agentId]);

  useEffect(() => {
    api.listProposals("all").then(
      (next) => setProposals(next.proposals),
      () => setProposals([]),
    );
  }, [pendingCount]);

  const reloadUser = useCallback(async () => {
    setUser(await api.getUserMemory());
    stamp();
  }, []);

  const reloadAgent = useCallback(async () => {
    setAgentMemory(await api.getAgentMemory(agentId));
  }, [agentId]);

  const saveUserMd = useCallback(async (text: string) => setUser(await api.putUserMd(text)), []);

  const saveFact = useCallback(
    async (name: string, body: FactBody) => {
      await api.putFact(name, body);
      await reloadUser();
    },
    [reloadUser],
  );

  const removeFact = useCallback(
    async (name: string) => {
      await api.deleteFact(name);
      await reloadUser();
    },
    [reloadUser],
  );

  const saveAgentMemory = useCallback(
    async (text: string) => setAgentMemory(await api.putAgentMemory(agentId, text)),
    [agentId],
  );

  const readNote = useCallback(
    async (day: string) => (await api.getNote(agentId, day)).body,
    [agentId],
  );

  const saveNote = useCallback(
    async (day: string, body: string) => {
      await api.putNote(agentId, day, body);
      await reloadAgent();
    },
    [agentId, reloadAgent],
  );

  const search = useCallback(
    async (query: string, onlyThisAgent: boolean) => {
      const found = await api.searchMemory(query, onlyThisAgent ? agentId : undefined);
      setHits(found.hits);
    },
    [agentId],
  );

  const decide = useCallback(
    async (id: string, approve: boolean) => {
      const decided = await api.decideProposal(id, approve);
      setProposals((all) => all.map((p) => (p.id === decided.id ? decided : p)));
      await reloadUser();
      await reloadAgent();
    },
    [reloadUser, reloadAgent],
  );

  const consolidate = useCallback(async () => {
    await api.consolidateMemory(agentId);
  }, [agentId]);

  const undo = useCallback(
    async (proposal: MemoryProposal) => {
      await api.putAgentMemory(proposal.agent_id, proposal.previous_body);
      await reloadAgent();
    },
    [reloadAgent],
  );

  return {
    user,
    agentMemory,
    proposals,
    hits,
    loadedAt,
    saveUserMd,
    saveFact,
    removeFact,
    saveAgentMemory,
    readNote,
    saveNote,
    search,
    decide,
    consolidate,
    undo,
  };
}
