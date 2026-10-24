export function StationReviewCard({ name, status }: { name: string; status: string }) { return <article className="workflow-card"><h2>{name}</h2><p className="status-label">{status}</p></article>; }
