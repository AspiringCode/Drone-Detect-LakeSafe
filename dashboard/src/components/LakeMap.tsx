import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { Drone, RiskZone } from "../lib/types";
import { droneMarkerColor, riskZoneStyle } from "../lib/mapStyle";

const LAKE_SAMMAMISH_CENTER: L.LatLngExpression = [47.581, -122.091];
const LAKE_SAMMAMISH_ZOOM = 13;

export interface RiskGeoJSON {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    geometry: GeoJSON.Geometry;
    properties: RiskZone;
  }>;
}

interface LakeMapProps {
  riskmap: RiskGeoJSON | null;
  drones: Drone[];
}

export function LakeMap({ riskmap, drones }: LakeMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const riskLayerRef = useRef<L.GeoJSON | null>(null);
  const markersRef = useRef<Map<string, L.CircleMarker>>(new Map());

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current).setView(LAKE_SAMMAMISH_CENTER, LAKE_SAMMAMISH_ZOOM);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !riskmap) return;
    riskLayerRef.current?.remove();
    riskLayerRef.current = L.geoJSON(riskmap as GeoJSON.GeoJsonObject, {
      style: (feature) => riskZoneStyle(feature!.properties as RiskZone),
    }).addTo(map);
  }, [riskmap]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const seen = new Set<string>();
    for (const drone of drones) {
      seen.add(drone.drone_id);
      const latlng: L.LatLngExpression = [drone.pos.lat, drone.pos.lon];
      let marker = markersRef.current.get(drone.drone_id);
      if (!marker) {
        marker = L.circleMarker(latlng, { radius: 8 }).addTo(map);
        markersRef.current.set(drone.drone_id, marker);
      }
      marker.setLatLng(latlng);
      const color = droneMarkerColor(drone.status);
      marker.setStyle({ color, fillColor: color, fillOpacity: 0.9 });
      marker.bindTooltip(
        `<span class="source-badge source-badge--${drone.source}">${drone.source.toUpperCase()}</span> ${drone.drone_id} &mdash; ${drone.status} &mdash; ${drone.assigned_zone ?? "unassigned"}`,
      );
    }
    for (const [id, marker] of markersRef.current) {
      if (!seen.has(id)) {
        marker.remove();
        markersRef.current.delete(id);
      }
    }
  }, [drones]);

  return <div ref={containerRef} className="lake-map" role="region" aria-label="Lake Sammamish operator map" />;
}
