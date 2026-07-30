import type { PublicLake } from "../lib/publicData";

export function PublicLakeMap({ lake }: { lake: PublicLake }) {
  return <section className="public-lake-map" aria-label={`${lake.name} public lake overview`}>
    <div className="public-lake-map__water" aria-hidden="true"><i /><i /><i /></div>
    <p className="panel-eyebrow">Community patrol area</p>
    <h2>{lake.name}</h2>
    <p>Patrol information is generalized for community safety and privacy.</p>
    <span className="public-status">{lake.public_status}</span>
  </section>;
}
