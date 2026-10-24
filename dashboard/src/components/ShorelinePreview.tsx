import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import type { Polygon, MultiPolygon } from "geojson";

export function ShorelinePreview({ geometry, onFailure }: { geometry: Polygon | MultiPolygon; onFailure?: () => void }) {
  const container = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!container.current) return;
    setFailed(false);
    let map: L.Map | undefined;
    let observer: ResizeObserver | undefined;
    try {
      map = L.map(container.current, { scrollWheelZoom: false });
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { attribution: "© OpenStreetMap contributors" }).addTo(map);
      const boundary = L.geoJSON(geometry, { style: { color: "#1479b8", weight: 2, fillOpacity: .15 } }).addTo(map);
      map.fitBounds(boundary.getBounds(), { padding: [24, 24] });
      if (typeof ResizeObserver !== "undefined") {
        observer = new ResizeObserver(() => map?.invalidateSize());
        observer.observe(container.current);
      }
    } catch { setFailed(true); onFailure?.(); }
    return () => { observer?.disconnect(); map?.remove(); };
  }, [geometry, onFailure]);
  return <section className="shoreline-preview" aria-label="Shoreline preview"><div ref={container} className="shoreline-preview__map" role="img" aria-label="Returned lake shoreline map"/>{failed && <p role="alert">The shoreline could not be drawn. Preview the lake again before continuing.</p>}</section>;
}
