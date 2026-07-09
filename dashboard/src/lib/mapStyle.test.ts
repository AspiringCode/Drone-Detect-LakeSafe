import { describe, expect, it } from "vitest";
import { droneMarkerColor, riskZoneStyle } from "./mapStyle";
import type { RiskZone } from "./types";

const mkZone = (score: number, isProxy: boolean): RiskZone => ({
  zone_id: "z1",
  centroid: { lat: 47.58, lon: -122.09 },
  polygon: [],
  risk_score: score,
  components: {},
  is_proxy: isProxy,
});

describe("riskZoneStyle", () => {
  it("adds a dashed outline and a proxy class for is_proxy zones", () => {
    const style = riskZoneStyle(mkZone(0.5, true));
    expect(style.dashArray).toBe("6 4");
    expect(style.className).toContain("risk-zone--proxy");
  });

  it("has no dash and no proxy class for non-proxy zones", () => {
    const style = riskZoneStyle(mkZone(0.5, false));
    expect(style.dashArray).toBeUndefined();
    expect(style.className).not.toContain("proxy");
  });

  it("colors a high-risk zone differently than a low-risk zone", () => {
    const low = riskZoneStyle(mkZone(0.0, false));
    const high = riskZoneStyle(mkZone(1.0, false));
    expect(low.color).not.toEqual(high.color);
  });
});

describe("droneMarkerColor", () => {
  it("returns a distinct color per status", () => {
    expect(droneMarkerColor("investigating")).not.toEqual(droneMarkerColor("idle"));
    expect(droneMarkerColor("patrolling")).not.toEqual(droneMarkerColor("returning"));
  });
});
