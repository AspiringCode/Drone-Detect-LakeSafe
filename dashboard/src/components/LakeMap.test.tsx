import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { LakeMap } from "./LakeMap";

const leaflet = vi.hoisted(() => ({ circleMarker: vi.fn(() => ({ addTo: vi.fn().mockReturnThis(), setLatLng: vi.fn(), setStyle: vi.fn(), bindTooltip: vi.fn(), remove: vi.fn() })) }));
vi.mock("leaflet", () => ({ default: { map: () => ({ setView: vi.fn().mockReturnThis(), remove: vi.fn() }), tileLayer: () => ({ addTo: vi.fn() }), geoJSON: () => ({ addTo: vi.fn() }), circleMarker: leaflet.circleMarker } }));

describe("LakeMap", () => {
  it("places a red station marker when given a shore station", () => {
    render(<LakeMap riskmap={null} drones={[]} stationLocation={{ lat: 47.606, lon: -122.09 }} />);
    expect(leaflet.circleMarker).toHaveBeenCalledWith([47.606, -122.09], expect.objectContaining({ color: "#c4332d" }));
  });
});
