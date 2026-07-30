import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { CivilianHomePage } from "./CivilianHomePage";

const fetcher = async (url: string) => ({
  ok: true,
  json: async () => url.endsWith("/lakes")
    ? [{ lake_id: "lake-1", name: "Lake Sammamish", approximate_center_geohash: "c23nb", public_status: "patrolling", refreshed_at: "2026-07-30T12:05:00Z" }]
    : url.endsWith("/alerts")
      ? [{ lake_id: "lake-1", category: "Safety notice", approximate_area_label: "North lake area", public_status: "active", occurred_at: "2026-07-30T12:00:00Z", published_at: "2026-07-30T12:05:00Z" }]
      : [{ lake_id: "lake-1", generalized_zone: "North lake area", public_state: "patrolling", observed_bucket: "2026-07-30T12:00:00Z", published_at: "2026-07-30T12:05:00Z" }],
});

describe("CivilianHomePage", () => {
  it("renders public patrol and alert summaries without operational fields", async () => {
    render(<MemoryRouter><CivilianHomePage fetcher={fetcher} /></MemoryRouter>);

    expect(await screen.findByText("Patrol presence")).toBeVisible();
    expect(screen.getAllByText("North lake area")).toHaveLength(2);
    expect(screen.queryByText(/battery|serial number|exact coordinates/i)).not.toBeInTheDocument();
  });
});
