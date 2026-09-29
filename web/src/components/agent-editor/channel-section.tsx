import type { AgentInfo } from "../../api/types";
import type { AgentDraft } from "../../hooks/use-agent-draft";
import { vi } from "../../i18n/vi";
import { CheckField, TextField } from "./fields";
import { IntegerField } from "./integer-field";

interface Props {
  form: AgentDraft;
  agent: AgentInfo;
  readOnly: boolean;
}

/**
 * The Telegram channel, and the skills the agent can already reach.
 *
 * The Telegram block holds the NAME of the environment variable that holds the token, and
 * there is no field for the token itself anywhere in this app. A secret typed into a
 * browser would be in the request body, the profile file and the browser's own form
 * history before it ever reached the bot.
 *
 * The skills folders are listed rather than edited: the profile reports the skills it
 * found, not the folders it looked in, so there is no baseline here to edit against.
 */
export function ChannelSection({ form, agent, readOnly }: Props) {
  const { draft, set } = form;
  const telegram = draft.telegram ?? null;

  return (
    <section className="editor-section" data-testid="section-channel">
      <h3>{vi.editor.sectionTelegram}</h3>
      {!agent.is_master && <p className="muted warn-text">{vi.editor.telegramOnlyMaster}</p>}
      <CheckField
        label={vi.editor.telegramEnabled}
        checked={telegram !== null}
        disabled={readOnly}
        onChange={(on) =>
          set(
            "telegram",
            on
              ? {
                  // What the file says beyond the two boxes, such as how long an
                  // approval waits, comes back with the channel.
                  ...agent.telegram,
                  token_env: agent.telegram?.token_env ?? "",
                  chat_id: agent.telegram?.chat_id ?? 0,
                }
              : null,
          )
        }
      />
      {telegram && (
        <TextField
          label={vi.editor.telegramTokenEnv}
          hint={vi.editor.telegramHint}
          value={telegram.token_env}
          disabled={readOnly}
          onChange={(v) => set("telegram", { ...telegram, token_env: v })}
        />
      )}
      {telegram && (
        // Checked before the save rather than left to the server: the bot answers only
        // this chat, and an id off by its sign sends the crew's replies nowhere.
        <IntegerField
          label={vi.editor.telegramChatId}
          hint={vi.editor.telegramChatIdHint}
          value={telegram.chat_id}
          disabled={readOnly}
          error={form.problems.chatId}
          onChange={(v) => set("telegram", { ...telegram, chat_id: v })}
        />
      )}

      <h3>{vi.editor.sectionSkills}</h3>
      {agent.skills.length === 0 ? (
        <p className="muted">{vi.editor.skillsEmpty}</p>
      ) : (
        <div className="row wrap" data-testid="skill-list">
          {agent.skills.map((skill) => (
            <code key={skill}>{skill}</code>
          ))}
        </div>
      )}
    </section>
  );
}
