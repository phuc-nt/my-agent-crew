import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../i18n/vi";
import { NO_FILTERS, filterRuns, sourceKind, sourceKinds, type RunFilters } from "../lib/run-filters";
import { coachAgent, fakeAgent, fakeRun } from "../test/fake-backend";
import { ActivityFilters } from "./activity-filters";

const runs = [
  fakeRun({ id: "web-ok", source: "chat", status: "done" }),
  fakeRun({ id: "web-bad", source: "chat", status: "error" }),
  fakeRun({ id: "job-bad", agent_id: "coach", source: "job:coach/brief", status: "error" }),
  fakeRun({ id: "tg-stop", agent_id: "coach", source: "telegram", status: "halted" }),
  fakeRun({ id: "wiki", agent_id: "coach", source: "memory:wiki", status: "done" }),
];
const ids = (filters: Partial<RunFilters>) => filterRuns(runs, { ...NO_FILTERS, ...filters }).map((r) => r.id);

describe("narrowing the recent runs", () => {
  it("keeps only runs that match every chosen chip", () => {
    expect(ids({})).toHaveLength(runs.length);
    expect(ids({ status: "error" })).toEqual(["web-bad", "job-bad"]);
    expect(ids({ status: "error", source: "schedule" })).toEqual(["job-bad"]);
    expect(ids({ agent: "coach", status: "error", source: "web" })).toEqual([]);
    expect(ids({ agent: "coach", source: "memory" })).toEqual(["wiki"]);
  });

  // The labels follow the sources the server actually writes, not a list made up here.
  it("names where a run came from by the first part of its source", () => {
    expect(sourceKind("chat")).toBe("web");
    expect(sourceKind("telegram")).toBe("telegram");
    expect(sourceKind("job:coach/brief")).toBe("schedule");
    expect(sourceKind("memory:consolidate")).toBe("memory");
    expect(sourceKind("delegate:c1")).toBe("delegate");
    expect(sourceKind("api")).toBe("api");
    expect(sourceKind("zalo:42")).toBe("zalo");
  });

  // A chip for a source with no run behind it is a dead end; the chosen one must stay
  // so it can be undone after the runs that matched it scrolled out of the page.
  it("offers the sources present, plus the one chosen", () => {
    expect(sourceKinds(runs, null)).toEqual(["web", "telegram", "schedule", "memory"]);
    expect(sourceKinds(runs.slice(0, 2), "api")).toEqual(["web", "api"]);
  });
});

describe("the filter chips", () => {
  function show(filters: RunFilters = NO_FILTERS, agents = [fakeAgent, coachAgent]) {
    const onChange = vitest.fn();
    render(<ActivityFilters filters={filters} agents={agents} sources={["web", "schedule"]} onChange={onChange} />);
    const group = (label: string) => within(screen.getByRole("group", { name: label }));
    return { onChange, group };
  }

  it("changes one group and leaves the others as they were", async () => {
    const { onChange, group } = show({ agent: "coach", status: null, source: "web" });

    await userEvent.click(group(vi.runFilters.status).getByRole("button", { name: vi.runFilters.statuses.error }));

    expect(onChange).toHaveBeenCalledWith({ agent: "coach", status: "error", source: "web" });
  });

  it("marks the chosen chip in each group, and 'all' where nothing is chosen", () => {
    const { group } = show({ agent: "coach", status: "halted", source: null });

    expect(group(vi.runFilters.agent).getByRole("button", { name: coachAgent.name })).toHaveAttribute("aria-pressed", "true");
    expect(group(vi.runFilters.status).getByRole("button", { name: vi.runFilters.statuses.halted })).toHaveAttribute("aria-pressed", "true");
    expect(group(vi.runFilters.source).getByRole("button", { name: vi.runFilters.all })).toHaveAttribute("aria-pressed", "true");
    expect(group(vi.runFilters.source).getByRole("button", { name: "Lịch" })).toHaveAttribute("aria-pressed", "false");
  });

  it("undoes one group's choice with its own 'all' chip", async () => {
    const { onChange, group } = show({ agent: "coach", status: "error", source: "schedule" });

    await userEvent.click(group(vi.runFilters.source).getByRole("button", { name: vi.runFilters.all }));

    expect(onChange).toHaveBeenCalledWith({ agent: "coach", status: "error", source: null });
  });

  // The run card's inline status words are lower case ("lỗi · 15:00"); as chips beside
  // "Tất cả" and "Lịch" they read as a row left unfinished.
  it("labels every chip in the same case, status chips included", () => {
    show();

    const labels = screen.getAllByRole("button").map((chip) => chip.textContent ?? "");
    expect(labels.length).toBeGreaterThan(0);
    for (const label of labels) expect(label[0]).toBe(label[0].toLocaleUpperCase("vi"));
  });

  // A phone folds the chips behind this toggle (run-log.css), so closed it still has to
  // say which narrowing is in force.
  it("folds behind one toggle that names the narrowing in force", async () => {
    show({ agent: "coach", status: "error", source: "schedule" });

    const toggle = screen.getByRole("button", { expanded: false });
    expect(toggle).toHaveTextContent(
      `${vi.runFilters.fold} · ${coachAgent.name} · ${vi.runFilters.statuses.error} · Lịch`,
    );
    await userEvent.click(toggle);

    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });

  it("names nothing on the toggle when nothing is narrowed", () => {
    show();

    expect(screen.getByRole("button", { expanded: false })).toHaveTextContent(new RegExp(`^${vi.runFilters.fold}$`));
  });

  it("offers no agent choice to a crew of one", () => {
    show(NO_FILTERS, [fakeAgent]);

    expect(screen.queryByRole("group", { name: vi.runFilters.agent })).not.toBeInTheDocument();
    expect(screen.getByRole("group", { name: vi.runFilters.status })).toBeInTheDocument();
  });
});
