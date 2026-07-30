import { DataFreshnessBadge } from "./DataFreshnessBadge";
import type { ZonePlanSummary } from "../lib/types";

export function ZonePlanStatus({ plan }: { plan: ZonePlanSummary | null }) {
  if (!plan) return <section className="panel-card plan-card"><p className="panel-eyebrow">Coverage</p><h2>Plan unavailable</h2><p className="panel-empty">No active coverage plan is available yet.</p></section>;
  return <section className="panel-card plan-card" aria-label="Autonomous coverage plan">
    <div className="panel-heading"><div><p className="panel-eyebrow">Coverage</p><h2>Active coverage plan</h2></div><DataFreshnessBadge freshThrough={plan.sourceFreshThrough} /></div>
    <dl className="plan-details"><div><dt>Algorithm</dt><dd>{plan.algorithmVersion}</dd></div><div><dt>Hotspot cells</dt><dd>{plan.hotspotCells}</dd></div><div><dt>Coverage cells</dt><dd>{plan.coverageCells}</dd></div></dl>
    {plan.activityDataUnavailable && <p className="coverage-notice">Activity data is temporarily unavailable; the current plan remains in place.</p>}
  </section>;
}
