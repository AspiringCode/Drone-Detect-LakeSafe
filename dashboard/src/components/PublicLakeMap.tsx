import { publicMapCenter, type PublicLake } from "../lib/publicData";
import { LakePreviewMap } from "./LakePreviewMap";

export function PublicLakeMap({ lake }: { lake: PublicLake }) {
  const center = publicMapCenter(lake.approximate_center_geohash);
  return <section className="public-lake-map" aria-label={`${lake.name} public lake overview`}>
    <div className="public-map-heading"><h2>{lake.name}</h2><p>Lake area</p></div>
    {center ? <LakePreviewMap name={lake.name} lat={center.lat} lon={center.lon} /> : <p className="public-map-unavailable">Map location is not available for this lake yet.</p>}
    {center && <p className="public-map-caption">Use the map to find the lake and nearby places.</p>}
  </section>;
}
