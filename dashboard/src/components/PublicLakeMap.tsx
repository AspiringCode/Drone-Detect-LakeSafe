import { publicMapCenter, type PublicLake } from "../lib/publicData";
import { LakePreviewMap } from "./LakePreviewMap";

export function PublicLakeMap({ lake }: { lake: PublicLake }) {
  const center = lake.map_bounds ? { lat: (lake.map_bounds[1]+lake.map_bounds[3])/2, lon: (lake.map_bounds[0]+lake.map_bounds[2])/2 } : publicMapCenter(lake.approximate_center_geohash);
  return <section className="public-lake-map" aria-label={`${lake.name} public lake overview`}>
    <div className="public-map-heading"><h2>{lake.name}</h2><p>Lake area</p></div>
    {center ? <LakePreviewMap name={lake.name} lat={center.lat} lon={center.lon} bounds={lake.map_bounds} interactive /> : <p className="public-map-unavailable">Map location is not available for this lake yet.</p>}
    {center && <p className="public-map-caption">Drag to explore. Use + and - to zoom, or pinch on a touch screen.</p>}
  </section>;
}
