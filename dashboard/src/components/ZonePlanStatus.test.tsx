import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ZonePlanSummary } from "../lib/types";
import { ZonePlanStatus } from "./ZonePlanStatus";


const plan = {
  planId: "plan-1",
  snapshotId: "snapshot-1",
  algorithmVersion: "risk-zone-v1",
  sourceFreshThrough: "2026-08-18T00:00:00Z",
  activityDataUnavailable: false,
  priorityCells: 2,
  proxyPriorityCells: 1,
  coverageCells: 4,
  sourceAttribution: [
    "King County Open Data — Freshwater Swim Beach Data and Water Quality Monitoring Sites",
  ],
} as ZonePlanSummary;


describe("ZonePlanStatus", () => {
  it("labels reviewed proxy priorities and baseline coverage transparently", () => {
    render(<ZonePlanStatus plan={plan} />);

    expect(screen.getByText("Patrol-priority areas")).toBeVisible();
    expect(screen.getByText("Baseline coverage areas")).toBeVisible();
    expect(screen.getByText("Proxy data")).toBeVisible();
    expect(screen.getByText("King County Open Data — Freshwater Swim Beach Data and Water Quality Monitoring Sites")).toBeVisible();
    expect(screen.getByText(/data (current|stale)/i)).toBeVisible();
  });

  it("describes unavailable reviewed priority data without implying an incident feed", () => {
    render(<ZonePlanStatus plan={{ ...plan, activityDataUnavailable: true }} />);

    const notice = screen.getByText(/reviewed priority data is unavailable/i);
    expect(notice).toHaveTextContent(/active.*baseline plan remains in place/i);
    expect(notice).not.toHaveTextContent(/incident/i);
  });
});
