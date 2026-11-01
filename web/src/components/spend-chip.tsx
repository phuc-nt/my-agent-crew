import type { OpenRouterReport, ProviderSpend, SpendInfo } from "../api/types";
import { useSpend } from "../hooks/use-spend";
import { vi } from "../i18n/vi";
import { formatUsd } from "./budget-indicator";
import { Icon } from "./ui/icon";
import { MetricRow, type Tone } from "./ui/metric-card";
import { PopoverChip } from "./ui/popover-chip";

const name = (provider: string) => vi.spend.providers[provider] ?? provider;

/** This month's figure for a provider: OpenRouter's own count when it gave one, since it
 *  covers the whole key; the crew's ledger otherwise. */
export function monthUsd(row: ProviderSpend, router: OpenRouterReport | null): number {
  if (row.provider === "openrouter" && router?.usage_monthly != null) return router.usage_monthly;
  return row.month_usd;
}

/** Amber under a tenth of OpenRouter's limit left, red when none is. */
export function spendTone(router: OpenRouterReport | null): Tone | undefined {
  if (router?.limit == null || router.limit_remaining == null) return undefined;
  if (router.limit_remaining <= 0) return "danger";
  return router.limit_remaining < router.limit * 0.1 ? "warn" : undefined;
}

/**
 * What the model providers have cost this month, kept in the header so it is always in
 * view: each billed provider's figure on the pill (the total alone on a phone, where the
 * title row is narrow), and today's, OpenRouter's own count and what is left under its
 * limit in the card. Nothing shows until there is a provider to report on.
 */
export function SpendChip({ compact = false }: { compact?: boolean }) {
  const spend = useSpend();
  if (!spend || spend.providers.length === 0) return null;
  return <SpendPill spend={spend} compact={compact} />;
}

export function SpendPill({ spend, compact }: { spend: SpendInfo; compact: boolean }) {
  const router = spend.openrouter;
  const rows = spend.providers;
  const total = rows.reduce((sum, row) => sum + monthUsd(row, router), 0);
  const label = compact
    ? formatUsd(total)
    : rows.map((row) => `${name(row.provider)} ${formatUsd(monthUsd(row, router))}`).join(" · ");
  return (
    <PopoverChip
      className="spend"
      testId="spend"
      tone={spendTone(router)}
      title={vi.spend.pillHint}
      popoverLabel={vi.spend.title}
      label={
        <>
          {/* A phone's title row has no room to spare: the figure says what it is. */}
          {!compact && <Icon name="coins" />}
          <span className="tabular">{label}</span>
        </>
      }
    >
      <h3 className="metric-card-title">{`${vi.spend.title} · ${vi.spend.month(spend.month)}`}</h3>
      {rows.map((row) => (
        <MetricRow
          key={row.provider}
          icon="coins"
          label={
            row.provider === "openrouter" && router
              ? `${name(row.provider)} · ${vi.spend.ledger}`
              : name(row.provider)
          }
          value={formatUsd(row.month_usd)}
          sub={[
            vi.spend.today(formatUsd(row.today_usd)),
            row.unknown_cost_calls > 0 ? vi.spend.unpriced(row.unknown_cost_calls) : "",
          ]
            .filter(Boolean)
            .join(" · ")}
          subTone={row.unknown_cost_calls > 0 ? "warn" : "muted"}
        />
      ))}
      {rows.some((row) => row.provider === "openrouter") && <RouterReport router={router} />}
      {rows.some((row) => row.provider === "anthropic") && (
        <p className="muted spend-note">{vi.spend.claudeNote}</p>
      )}
    </PopoverChip>
  );
}

function RouterReport({ router }: { router: OpenRouterReport | null }) {
  if (!router) return <p className="muted spend-note">{vi.spend.routerUnread}</p>;
  const left =
    router.limit != null && router.limit_remaining != null
      ? vi.spend.routerLeft(formatUsd(router.limit_remaining), formatUsd(router.limit))
      : vi.spend.routerNoLimit;
  return (
    <MetricRow
      icon="info"
      label={vi.spend.routerReported}
      value={router.usage_monthly != null ? formatUsd(router.usage_monthly) : "—"}
      sub={`${vi.spend.routerReportedSub(formatUsd(router.usage_daily ?? 0), formatUsd(router.usage_weekly ?? 0))} · ${left}`}
      subTone={spendTone(router) ?? "muted"}
    />
  );
}
