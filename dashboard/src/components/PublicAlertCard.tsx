import { publishedTime, type PublicAlert } from "../lib/publicData";

export function PublicAlertCard({ alert }: { alert: PublicAlert }) {
  return <article className="public-alert-card">
    <span className="public-alert-card__dot" aria-hidden="true" />
    <div><h3>{alert.category}</h3><p>{alert.approximate_area_label}</p><p>{alert.public_status.replace(/_/g, " ")} · Published {publishedTime(alert.published_at)}</p></div>
  </article>;
}
