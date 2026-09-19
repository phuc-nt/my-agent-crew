import { useEffect, useState } from "react";
import { api } from "./api/client";
import type { SettingsInfo } from "./api/types";
import { ApprovalBar } from "./components/approval-bar";
import { Composer } from "./components/composer";
import { ConversationHeader } from "./components/conversation-header";
import { ConversationList } from "./components/conversation-list";
import { MessageThread } from "./components/message-thread";
import { SettingsPanel } from "./components/settings-panel";
import { useConversations } from "./hooks/use-conversations";
import { useThread } from "./hooks/use-thread";
import { vi } from "./i18n/vi";

export function App() {
  const list = useConversations();
  const thread = useThread(list.activeId);
  const [settings, setSettings] = useState<SettingsInfo | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [draft, setDraft] = useState<string | undefined>(undefined);
  const [queued, setQueued] = useState<{ id: string; text: string } | null>(null);

  useEffect(() => {
    api.settings().then(setSettings, () => setSettings(null));
  }, []);

  // A message typed before any conversation exists waits until the new one has loaded.
  const { send: threadSend, detail } = thread;
  useEffect(() => {
    if (queued && detail?.id === queued.id) {
      setQueued(null);
      void threadSend(queued.text);
    }
  }, [queued, detail?.id, threadSend]);

  const active = list.conversations.find((c) => c.id === list.activeId) ?? null;
  const echoOnly = settings !== null && settings.providers.every((p) => p === "fake");

  const send = async (text: string) => {
    if (list.activeId) return thread.send(text);
    const created = await list.create();
    if (created) setQueued({ id: created.id, text });
  };

  const rename = () => {
    if (!active) return;
    const title = window.prompt(vi.renamePrompt, active.title);
    if (title && title !== active.title) void list.patch(active.id, { title });
  };

  const remove = (id: string) => {
    if (window.confirm(vi.confirmDelete)) void list.remove(id);
  };

  const { state } = thread;
  const notice = state.notice && (
    <div className={`notice ${state.notice.kind}`} role="status">
      {state.notice.kind === "halted"
        ? state.notice.text === "budget"
          ? vi.haltedBudget
          : vi.haltedMaxSteps
        : vi.errorPrefix + state.notice.text}
    </div>
  );

  return (
    <div className="layout">
      <ConversationList
        conversations={list.conversations}
        activeId={list.activeId}
        onSelect={list.select}
        onCreate={() => void list.create()}
        onDelete={remove}
      />
      <main className="main">
        {active ? (
          <ConversationHeader
            conversation={active}
            spentUsd={state.spentUsd}
            unknownCostCalls={state.unknownCostCalls}
            skills={settings?.skills ?? []}
            onRename={rename}
            onToggleAutonomous={(value) => void list.patch(active.id, { autonomous: value })}
            onToggleSkill={(name, attached) => {
              const next = attached
                ? [...active.skills, name]
                : active.skills.filter((s) => s !== name);
              void list.patch(active.id, { skills: next });
            }}
            onOpenSettings={() => setSettingsOpen(true)}
          />
        ) : (
          <header className="conversation-header">
            <h1>{vi.appName}</h1>
            <button type="button" className="ghost" onClick={() => setSettingsOpen(true)}>
              ⚙ {vi.settings}
            </button>
          </header>
        )}
        {list.error && <div className="notice error">{vi.loadFailed}</div>}
        {notice}
        <MessageThread
          items={state.items}
          streaming={state.streaming}
          busy={state.busy}
          echoOnly={echoOnly}
          onSuggestion={(text) => setDraft(text)}
        />
        {state.pending && (
          <ApprovalBar pending={state.pending} busy={state.busy} onDecide={(ok) => void thread.decide(ok)} />
        )}
        {active?.over_budget && !state.busy && <div className="notice halted">{vi.overBudget}</div>}
        <Composer
          disabled={state.pending !== null}
          busy={state.busy}
          draft={draft}
          onSend={(text) => {
            setDraft(undefined);
            void send(text);
          }}
          onStop={thread.stop}
        />
      </main>
      {settingsOpen && <SettingsPanel settings={settings} onClose={() => setSettingsOpen(false)} />}
    </div>
  );
}
