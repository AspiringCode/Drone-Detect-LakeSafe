import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LakeMap } from "./LakeMap";

const leaflet = vi.hoisted(() => {
  const mapInstance = { setView: vi.fn().mockReturnThis(), fitBounds: vi.fn(), remove: vi.fn() };
  return {
    map: vi.fn(() => mapInstance),
    mapInstance,
    circleMarker: vi.fn(() => ({ addTo: vi.fn().mockReturnThis(), setLatLng: vi.fn(), setStyle: vi.fn(), bindTooltip: vi.fn(), remove: vi.fn() })),
  };
});
vi.mock("leaflet", () => ({ default: { map: leaflet.map, tileLayer: () => ({ addTo: vi.fn() }), geoJSON: () => ({ addTo: vi.fn().mockReturnThis(), getBounds: () => ({ isValid: () => true }), remove: vi.fn() }), circleMarker: leaflet.circleMarker } }));

describe("LakeMap", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fits geometry once and allows explicit reset without overriding later map interaction", () => {
    const riskmap = { type: "FeatureCollection", features: [] } as const;
    const props = { lakeName: "Lake", lakeCenter: {lat: 1, lon: 2}, riskmap: riskmap as never, drones: [] };
    const view = render(<LakeMap {...props}/>);
    expect(leaflet.mapInstance.fitBounds).toHaveBeenCalledOnce();
    view.rerender(<LakeMap {...props} riskmap={{...riskmap} as never}/>);
    expect(leaflet.mapInstance.fitBounds).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", {name:"Reset view"}));
    expect(leaflet.mapInstance.fitBounds).toHaveBeenCalledTimes(2);
  });

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
