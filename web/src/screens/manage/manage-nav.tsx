import type { RefObject, UIEvent } from "react";
import type { RunInfo } from "../../api/types";
import { Brand } from "../../components/ui/brand-mark";
import { Icon, type IconName } from "../../components/ui/icon";
import type { ManageSection } from "../../hooks/use-route";
import { vi } from "../../i18n/vi";
import type { ManageProps } from "./manage-props";

export const LABELS: Record<ManageSection, string> = {
  activity: vi.activity,
  approvals: vi.approvalsTab,
  crew: vi.crew.tab,
  tools: vi.manage.tools,
  jobs: vi.jobs,
  memory: vi.memory.tab,
  canvas: vi.canvas.tab,
  costs: vi.costs,
  connections: vi.manage.connections,
  settings: vi.settings,
};

/** An icon per section, so the list can be scanned by shape before it is read. */
const ICONS: Record<ManageSection, IconName> = {
  activity: "activity",
  approvals: "approvals",
  costs: "coins",
  crew: "users",
  tools: "wrench",
  jobs: "clock",
  memory: "book",
  canvas: "document",
  connections: "plug",
  settings: "sliders",
};

/**
 * The sections in three groups rather than one list of ten: what to keep an eye on,
 * who is on the team and what they can do, and how the install is wired. Grouped, the
 * section a person wants is found by its kind first — "is this about the team?" — which
 * is how the question arrives, instead of by reading the list top to bottom.
 */
export const NAV_GROUPS: { key: keyof typeof vi.manage.groups; sections: ManageSection[] }[] = [
  { key: "watch", sections: ["activity", "approvals", "costs"] },
  { key: "crew", sections: ["crew", "tools", "jobs", "memory", "canvas"] },
  { key: "system", sections: ["connections", "settings"] },
];

interface NavProps extends Pick<ManageProps, "section" | "onNavigate" | "onBackToChat"> {
  /** The current section's entry, which the screen keeps in view. */
  active: RefObject<HTMLButtonElement | null>;
  onNavScroll: (event: UIEvent<HTMLElement>) => void;
  running: number;
  failed: RunInfo[];
  awaiting: RunInfo[];
  pendingProposals: number;
  failing: number;
}

/** The sections to choose from, each with what it has waiting. It holds no state of its own. */
export function ManageNav(props: NavProps) {
  const { active, onNavScroll, running, failed, awaiting, pendingProposals, failing } = props;
  // The number alone is ambiguous once an entry can carry two, so each says what it counts.
  const count = (n: number, tone: string, says: string) => (
    <span className={`badge ${tone}`}>
      {` ${n}`}
      <span className="sr-only"> {says}</span>
    </span>
  );
  const badge = (section: ManageSection) => {
    if (section === "activity")
      return (
        <>
          {running > 0 && count(running, "live", vi.manage.liveBadge)}
          {failed.length > 0 && count(failed.length, "warn", vi.manage.failedBadge)}
        </>
      );
    if (section === "approvals" && awaiting.length > 0) return count(awaiting.length, "warn", vi.manage.waitingBadge);
    if (section === "memory" && pendingProposals > 0)
      return <span className="badge warn"> {pendingProposals}</span>;
    // Only a failure earns a count here: a schedule that ran fine or never ran yet is
    // not something to go and look at.
    if (section === "jobs" && failing > 0)
      return (
        <span className="badge danger" title={vi.jobRow.failing(failing)} data-testid="jobs-failing">
          {/* A bare red number reads as "1" to a screen reader; the sentence says what of. */}
          <span aria-hidden="true">{failing}</span>
          <span className="sr-only">{vi.jobRow.failing(failing)}</span>
        </span>
      );
    return null;
  };

  return (
    <nav className="manage-nav" aria-label={vi.manage.nav} onScroll={onNavScroll}>
      <div className="manage-nav-head">
        <Brand />
      </div>
      <button type="button" className="ghost back-to-chat" onClick={props.onBackToChat}>
        {vi.manage.backToChat}
      </button>
      <div className="manage-nav-groups" onScroll={onNavScroll}>
        {NAV_GROUPS.map((group) => (
          <div className="manage-nav-group" key={group.key}>
            <p className="manage-nav-label">{vi.manage.groups[group.key]}</p>
            <ul>
              {group.sections.map((section) => (
                <li key={section}>
                  <button
                    type="button"
                    className={section === props.section ? "active" : ""}
                    aria-current={section === props.section ? "page" : undefined}
                    ref={section === props.section ? active : undefined}
                    onClick={() => props.onNavigate(section)}
                  >
                    <Icon name={ICONS[section]} />
                    <span className="manage-nav-name">{LABELS[section]}</span>
                    {badge(section)}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </nav>
  );
}
