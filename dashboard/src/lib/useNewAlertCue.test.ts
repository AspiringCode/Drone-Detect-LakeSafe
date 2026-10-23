import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useNewAlertCue } from "./useNewAlertCue";
import type { Alert } from "./types";

const at = (iso: string): Alert => ({ alert_id: `a-${iso}`, created_at: iso, location: { lat: 47.592, lon: -122.032 }, detection_mode: "thermal-cv", drone_id: "d-1", thermal_clip_ref: null, confirmed: true, source: "real", latency_ms: 0 });
const opened = Date.parse("2026-10-22T20:00:00Z");

describe("useNewAlertCue", () => {
  afterEach(() => { document.title = "LakeSafe"; });

  it("cues once for a real alert raised after the page opened, never for older or simulated ones", () => {
    document.title = "LakeSafe";
    const { result, rerender } = renderHook(({ alert }) => useNewAlertCue(alert, () => opened), { initialProps: { alert: at("2026-10-22T19:59:00Z") as Alert | null } });
    expect(result.current).toBe("");
    rerender({ alert: { ...at("2026-10-22T20:01:00Z"), source: "simulated" } });
    expect(result.current).toBe("");
    const fresh = at("2026-10-22T20:02:00Z");
    rerender({ alert: fresh });
    expect(result.current).toContain("New real drone alert at 47.59200, -122.03200");
    expect(document.title).toBe("● New alert — LakeSafe");
    rerender({ alert: { ...fresh } });
    expect(document.title).toBe("● New alert — LakeSafe");
    window.dispatchEvent(new Event("focus"));
    expect(document.title).toBe("LakeSafe");
  });
});
