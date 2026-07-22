import { useEffect, useRef } from "react";
import L from "leaflet";

type LakePreviewMapProps = {
  name: string;
  lat: number;
  lon: number;
};

export function LakePreviewMap({ name, lat, lon }: LakePreviewMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const map = L.map(containerRef.current, {
      attributionControl: false,
      boxZoom: false,
      doubleClickZoom: false,
      dragging: false,
      keyboard: false,
      scrollWheelZoom: false,
      touchZoom: false,
      zoomControl: false,
    }).setView([lat, lon], 12);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png").addTo(map);
    return () => { map.remove(); };
  }, [lat, lon]);

  return (
    <div className="lake-preview" role="img" aria-label={`${name} map preview`}>
      <div ref={containerRef} className="lake-preview-map" />
      <span className="lake-preview__attribution">© OpenStreetMap</span>
    </div>
  );
}
