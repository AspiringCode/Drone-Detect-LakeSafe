import type { PublicPatrolPresence } from "../lib/publicData";

export function PublicPatrolSummary({ presence }: { presence: PublicPatrolPresence[] }) {
  return <section className="public-patrol-summary" aria-label="Patrol presence">
    <p className="panel-eyebrow">Public overview</p><h2>Patrol presence</h2>
    {presence.length ? <ul>{presence.map((item) => <li key={`${item.generalized_zone}-${item.published_at}`}><span className="status-dot" aria-hidden="true" /><strong>{item.generalized_zone}</strong><span>{item.public_state}</span></li>)}</ul> : <p>No current public patrol update.</p>}
  </section>;
}
