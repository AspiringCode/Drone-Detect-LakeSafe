import { describe, expect, it } from "vitest";
import { publicMapCenter, publishedTime } from "./publicData";

describe("public map locations", () => {
  it("uses the center of the published geohash area", () => {
    expect(publicMapCenter("0")).toEqual({ lat: -67.5, lon: -157.5 });
    expect(publicMapCenter("Z")).toEqual({ lat: 67.5, lon: 157.5 });
  });
  it("does not invent a location for absent or invalid public data", () => {
    for (const value of [null, undefined, "", "invalid", "zzzzzzzzzzzzz", "47.6,-122.1"]) expect(publicMapCenter(value)).toBeNull();
    expect(publishedTime("not a timestamp")).toBe("Time unavailable");
  });
});
