const STALE_AFTER_MS = 24 * 60 * 60 * 1000;

export function DataFreshnessBadge({ freshThrough, now = new Date() }: { freshThrough: string | null; now?: Date }) {
  const date = freshThrough ? new Date(freshThrough) : null;
  if (!date || Number.isNaN(date.getTime())) return <span className="data-freshness data-freshness--unknown">Freshness unavailable</span>;
  const stale = now.getTime() - date.getTime() > STALE_AFTER_MS;
  return <span className={`data-freshness${stale ? " data-freshness--stale" : ""}`} title={date.toLocaleString()}>{stale ? "Data stale" : `Data current ${date.toLocaleDateString()}`}</span>;
}
