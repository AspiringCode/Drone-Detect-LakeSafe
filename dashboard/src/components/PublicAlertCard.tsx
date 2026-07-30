import type { PublicAlert } from "../lib/publicData";

export function PublicAlertCard({ alert }: { alert: PublicAlert }) {
  return <article className="public-alert-card">
    <span className="public-alert-card__dot" aria-hidden="true" />
    <div><p className="panel-eyebrow">{alert.public_status}</p><h3>{alert.category}</h3><p>{alert.approximate_area_label}</p></div>
  </article>;
}
