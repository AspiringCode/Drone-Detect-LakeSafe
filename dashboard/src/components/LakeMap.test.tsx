import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LakeMap } from "./LakeMap";

const leaflet = vi.hoisted(() => {
  const mapInstance = { setView: vi.fn().mockReturnThis(), remove: vi.fn() };
  return {
    map: vi.fn(() => mapInstance),
    mapInstance,
    circleMarker: vi.fn(() => ({ addTo: vi.fn().mockReturnThis(), setLatLng: vi.fn(), setStyle: vi.fn(), bindTooltip: vi.fn(), remove: vi.fn() })),
  };
});
vi.mock("leaflet", () => ({ default: { map: leaflet.map, tileLayer: () => ({ addTo: vi.fn() }), geoJSON: () => ({ addTo: vi.fn() }), circleMarker: leaflet.circleMarker } }));

describe("LakeMap", () => {
  beforeEach(() => vi.clearAllMocks());

  it.each([
    ["Pine Lake", 47.587, -122.052],
    ["Beaver Lake", 47.585, -121.997],
  ])("centers and labels the %s operator map", (lakeName, lat, lon) => {
    render(<LakeMap lakeName={lakeName} lakeCenter={{ lat, lon }} riskmap={null} drones={[]} />);

    expect(leaflet.mapInstance.setView).toHaveBeenCalledWith([lat, lon], 13);
    expect(screen.getByRole("region", { name: `${lakeName} operator map` })).toBeVisible();
  });

  it("places a red station marker when given a shore station", () => {
    render(<LakeMap lakeName="Pine Lake" lakeCenter={{ lat: 47.587, lon: -122.052 }} riskmap={null} drones={[]} stationLocation={{ lat: 47.606, lon: -122.09 }} />);
    expect(leaflet.circleMarker).toHaveBeenCalledWith([47.606, -122.09], expect.objectContaining({ color: "#c4332d" }));
  });
});
