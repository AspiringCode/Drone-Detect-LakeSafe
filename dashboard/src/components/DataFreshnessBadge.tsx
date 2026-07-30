export function DataFreshnessBadge({ freshThrough }: { freshThrough: string | null }) {
  if (!freshThrough) return <span className="data-freshness data-freshness--unknown">Freshness unavailable</span>;
  const date = new Date(freshThrough);
  return <span className="data-freshness" title={date.toLocaleString()}>Data current {date.toLocaleDateString()}</span>;
}
