import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DataFreshnessBadge } from "./DataFreshnessBadge";

describe("DataFreshnessBadge", () => {
  it("truthfully labels stale and unknown source data", () => {
    render(<><DataFreshnessBadge freshThrough="2026-07-27T00:00:00Z" now={new Date("2026-07-29T01:00:00Z")} /><DataFreshnessBadge freshThrough={null} now={new Date("2026-07-29T01:00:00Z")} /></>);
    expect(screen.getByText("Data stale")).toBeVisible();
    expect(screen.getByText("Freshness unavailable")).toBeVisible();
  });
});
