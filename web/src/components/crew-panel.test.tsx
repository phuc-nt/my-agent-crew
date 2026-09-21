import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../i18n/vi";
import { coachAgent, coderTemplate, fakeAgent } from "../test/fake-backend";
import { CrewPanel } from "./crew-panel";

const master = { ...fakeAgent, name: "Trợ lý", delegates: ["coach"] };
const coach = {
  ...coachAgent,
  telegram: { token_env: "COACH_TOKEN", chat_id: 1 },
  commands: [{ name: "brief", description: "Bản tin sáng", path: "/h/agents/coach/.agents/commands/brief.md" }],
  hooks: 2,
  kits: ["/h/agents/coach/.agents"],
};

describe("CrewPanel", () => {
  it("shows the master first, then each member with what the master can hand it", () => {
    render(
      <CrewPanel
        agents={[coach, master]}
        master={master}
        templates={[]}
        liveByAgent={{ coach: 1 }}
        onInstall={() => Promise.reject(new Error("unused"))}
      />,
    );
    expect(screen.getByText(vi.crew.intro("Trợ lý"))).toBeInTheDocument();
    const cards = screen.getAllByTestId("crew-agent");
    expect(cards[0]).toHaveTextContent("Trợ lý");
    expect(cards[0]).toHaveTextContent(vi.crew.master);
    expect(cards[0]).not.toHaveTextContent(vi.crew.delegatable);
    expect(cards[1]).toHaveTextContent("HLV sức khoẻ");
    expect(cards[1]).toHaveTextContent(vi.crew.delegatable);
    expect(cards[1]).toHaveTextContent(vi.runStatus.running);
    expect(cards[1]).toHaveTextContent(vi.agentSchedules(1));
    expect(cards[1]).toHaveTextContent(vi.crew.telegram);
    expect(cards[1]).not.toHaveTextContent("COACH_TOKEN");
    expect(cards[1]).toHaveTextContent(vi.agentCommands(1));
    expect(cards[1]).toHaveTextContent(vi.agentHooks(2));
    expect(cards[1]).toHaveTextContent("/h/agents/coach/.agents");
    expect(within(cards[1]).getByTitle(/\/brief — Bản tin sáng/)).toBeInTheDocument();
    expect(cards[0]).not.toHaveTextContent(vi.agentHooks(0));
    expect(cards[0]).not.toHaveTextContent(vi.agentKits);
    expect(screen.queryByTestId("template-list")).not.toBeInTheDocument();
  });

  it("installs a bundled template with one click and says when a restart is still needed", async () => {
    const onInstall = vitest.fn().mockResolvedValue({ installed: ["coder"], live: ["coder"], needs_restart: true });
    render(
      <CrewPanel agents={[master]} master={master} templates={[coderTemplate]} liveByAgent={{}} onInstall={onInstall} />,
    );
    const list = screen.getByTestId("template-list");
    expect(list).toHaveTextContent("Coder");
    expect(list).toHaveTextContent(vi.toolCount.replace("{n}", "2"));
    await userEvent.click(within(list).getByRole("button", { name: vi.crew.install }));
    expect(onInstall).toHaveBeenCalledWith("coder");
    const notice = await screen.findByRole("status");
    expect(notice).toHaveTextContent(vi.crew.installed(["coder"]));
    expect(notice).toHaveTextContent(vi.crew.needsRestart);
  });

  it("reports a failed install and marks templates already in the crew", async () => {
    const onInstall = vitest.fn().mockRejectedValue(new Error("agent coder already exists"));
    const { rerender } = render(
      <CrewPanel agents={[master]} master={master} templates={[coderTemplate]} liveByAgent={{}} onInstall={onInstall} />,
    );
    await userEvent.click(screen.getByRole("button", { name: vi.crew.install }));
    expect(await screen.findByRole("status")).toHaveTextContent(vi.crew.installFailed("agent coder already exists"));

    const coder = { ...fakeAgent, id: "coder", name: "Coder", is_master: false };
    rerender(
      <CrewPanel agents={[master, coder]} master={master} templates={[coderTemplate]} liveByAgent={{}} onInstall={onInstall} />,
    );
    const list = screen.getByTestId("template-list");
    expect(within(list).queryByRole("button", { name: vi.crew.install })).not.toBeInTheDocument();
    expect(list).toHaveTextContent(vi.crew.alreadyInstalled);
  });
});
