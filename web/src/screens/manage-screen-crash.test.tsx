import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../i18n/vi";
import { FakeBackend, fakeAgent } from "../test/fake-backend";
import { ManageScreen } from "./manage-screen";
import type { ManageSection } from "../hooks/use-route";

// The costs page stands in for any section that throws while rendering.
vitest.mock("../components/stats-panel", () => ({
  StatsPanel: () => {
    throw new Error("vỡ");
  },
}));

beforeEach(() => {
  vitest.stubGlobal("fetch", new FakeBackend().fetch);
  vitest.spyOn(console, "error").mockImplementation(() => undefined);
});

function screenAt(section: ManageSection) {
  return (
    <ManageScreen
      section={section}
      runs={[]}
      liveRuns={[]}
      attention={[]}
      jobs={[]}
      stats={null}
      settings={null}
      agents={[fakeAgent]}
      agentId="default"
      agentName={() => "Agent"}
      master={fakeAgent}
      templates={[]}
      liveByAgent={{}}
      onInstall={() => Promise.reject(new Error("không cài"))}
      onEditAgent={() => undefined}
      onReplayRun={() => undefined}
      onReloadCrew={() => undefined}
      onNavigate={() => undefined}
      onBackToChat={() => undefined}
      onOpenConversation={() => undefined}
      onRunJob={() => undefined}
      onToggleJob={() => undefined}
    />
  );
}

describe("a section that breaks", () => {
  it("keeps the navigation standing, so another page is one click away", () => {
    render(screenAt("costs"));

    expect(screen.getByRole("alert")).toHaveTextContent(vi.crashed);
    expect(screen.getByRole("navigation", { name: vi.manage.nav })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: vi.jobs })).toBeInTheDocument();
  });

  it("is left behind once the person moves to another page", () => {
    const { rerender } = render(screenAt("costs"));

    rerender(screenAt("jobs"));

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText(vi.jobsEmpty)).toBeInTheDocument();
  });
});
