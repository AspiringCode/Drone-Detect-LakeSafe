import { publishedTime, type PublicPatrolPresence } from "../lib/publicData";

export function PublicPatrolSummary({ presence }: { presence: PublicPatrolPresence[] }) {
  return <section className="public-patrol-summary" aria-label="Patrol presence">
    <h2>Patrol presence</h2>
    {presence.length ? <ul>{presence.map((item) => <li key={`${item.generalized_zone}-${item.published_at}`}><div><strong>{item.generalized_zone}</strong><p>{item.public_state.replace(/_/g, " ")}</p><p className="field-help">Published {publishedTime(item.published_at)}</p></div></li>)}</ul> : <p>No current public patrol update.</p>}
    <p className="field-help">Published activity does not confirm current conditions.</p>
  </section>;
}
