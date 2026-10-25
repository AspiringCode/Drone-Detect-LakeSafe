import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

type LakePreviewMapProps = {
  name: string;
  lat: number;
  lon: number;
  bounds?: [number, number, number, number] | null;
  interactive?: boolean;
};

export function LakePreviewMap({ name, lat, lon, bounds, interactive = false }: LakePreviewMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const resetRef = useRef<() => void>(() => {});
  const boundsKey = JSON.stringify(bounds);

  useEffect(() => {
    if (!containerRef.current) return;
    const map = L.map(containerRef.current, {
      attributionControl: false,
      boxZoom: interactive,
      doubleClickZoom: interactive,
      dragging: interactive,
      keyboard: interactive,
      scrollWheelZoom: false,
      touchZoom: interactive,
      zoomControl: interactive,
    });
    const reset = () => {
      if (bounds && bounds.length === 4 && bounds.every(Number.isFinite) && bounds[0] < bounds[2] && bounds[1] < bounds[3]) {
        map.fitBounds([[bounds[1],bounds[0]],[bounds[3],bounds[2]]], { padding: [16,16], maxZoom: 16 });
      } else map.setView([lat, lon], 14);
    };
    resetRef.current = reset;
    reset();
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png").addTo(map);
    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(() => map.invalidateSize()) : null;
    observer?.observe(containerRef.current);
    return () => { observer?.disconnect(); map.remove(); };
  }, [lat, lon, boundsKey, interactive]);

  return (
    <div className={`lake-preview${interactive ? " lake-preview--interactive" : ""}`} role={interactive ? "region" : "img"} aria-label={interactive ? `${name} interactive lake map` : `${name} map preview`}>
      <div ref={containerRef} className="lake-preview-map" />
      {interactive && <button type="button" className="button-secondary public-map-reset" onClick={() => resetRef.current()}>Reset lake view</button>}
      <span className="lake-preview__attribution">© OpenStreetMap</span>
    </div>
  );
}
