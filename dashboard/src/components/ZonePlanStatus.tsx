import { DataFreshnessBadge } from "./DataFreshnessBadge";
import type { ZonePlanSummary } from "../lib/types";

export function ZonePlanStatus({ plan }: { plan: ZonePlanSummary | null }) {
  if (!plan) return <section className="panel-card plan-card"><p className="panel-eyebrow">Coverage</p><h2>Plan unavailable</h2><p className="panel-empty">No active coverage plan is available yet.</p></section>;
  return <section className="panel-card plan-card" aria-label="Autonomous coverage plan">
    <div className="panel-heading"><div><p className="panel-eyebrow">Coverage</p><h2>Active coverage plan</h2></div><DataFreshnessBadge freshThrough={plan.sourceFreshThrough} /></div>
    <dl className="plan-details"><div><dt>Algorithm</dt><dd>{plan.algorithmVersion}</dd></div><div><dt>Patrol-priority areas</dt><dd>{plan.priorityCells}</dd></div><div><dt>Proxy-priority areas</dt><dd>{plan.proxyPriorityCells}</dd></div><div><dt>Baseline coverage areas</dt><dd>{plan.coverageCells + plan.fallbackCells}</dd></div></dl>
    {plan.fallbackCells > 0 && <p className="coverage-notice">Fallback coverage: {plan.fallbackCells === 1 ? "one whole-lake area is" : `${plan.fallbackCells} areas are`} patrolled until enough reviewed priority data is available to divide the lake.</p>}
    {plan.proxyPriorityCells > 0 && <p><span className="source-badge source-badge--simulated">Proxy data</span></p>}
    {plan.sourceAttribution.length > 0 && <p className="plan-attribution"><strong>Source:</strong> {plan.sourceAttribution.join("; ")}</p>}
    {plan.activityDataUnavailable && <p className="coverage-notice">Reviewed priority data is unavailable; the active baseline plan remains in place.</p>}
  </section>;
}
