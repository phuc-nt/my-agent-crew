/**
 * The switch for watching a canvas fill in while the agent writes it, on the settings page.
 *
 * It is the person's choice for the device in their hand, kept by the browser, where everything
 * else on that page is the machine's configuration and only read there. So it is a card of its
 * own, laid out as one of that page's cards, and needs nothing from the server to show.
 */

import { useLivePreview } from "../../hooks/use-live-preview";
import { vi } from "../../i18n/vi";
import { MetricCard, SwitchRow } from "../ui/metric-card";

export function LivePreviewSetting() {
  const text = vi.canvas.writing;
  const preview = useLivePreview();
  return (
    <div className="metric-grid">
      <MetricCard title={vi.canvas.tab}>
        <SwitchRow label={text.preview} checked={preview.enabled} onChange={preview.set} sub={text.previewDevice} />
        {/* Outside the label, so it is read out when it appears and is no part of the switch's name. */}
        {preview.tabOnly && (
          <div className="metric-sub warn" role="status">
            {text.previewTabOnly}
          </div>
        )}
      </MetricCard>
    </div>
  );
}
