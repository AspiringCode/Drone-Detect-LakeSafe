import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AlertsPage } from "./AlertsPage";
import { ReportsPage } from "./ReportsPage";

const alert = {
  alert_id: "alert-1",
  created_at: "2026-07-21T20:00:00Z",
  location: { lat: 47.58, lon: -122.09 },
  detection_mode: "thermal",
  drone_id: "drone-2",
  thermal_clip_ref: null,
  confirmed: true,
  source: "simulated",
  latency_ms: 820,
};

function dependencies() {
  const client = {
    auth: {
      getUser: vi.fn().mockResolvedValue({ data: { user: { email: "operator@example.com" } }, error: null }),
      signOut: vi.fn().mockResolvedValue({ error: null }),
    },
    from: vi.fn((table: string) => table === "organizations"
      ? { select: vi.fn().mockResolvedValue({ data: [{ org_id: "org-demo", name: "LakeSafe Demo Station" }], error: null }) }
      : { select: vi.fn(() => ({ order: vi.fn().mockResolvedValue({ data: [{ lake_id: "lake-sammamish", name: "Lake Sammamish" }], error: null }) })) }),
  };
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => [alert] });
  return { client, fetcher };
}

describe("operations data pages", () => {
  it("populates Alerts with lake-scoped backend data", async () => {
    const { client, fetcher } = dependencies();
    render(<MemoryRouter><AlertsPage client={client as never} fetcher={fetcher as never} /></MemoryRouter>);

    expect(await screen.findByRole("heading", { name: "Active alerts" })).toBeInTheDocument();
    expect(await screen.findByText("Lake Sammamish")).toBeInTheDocument();
    expect(screen.getByText("drone-2")).toBeInTheDocument();
    expect(screen.getByText("Confirmed")).toBeInTheDocument();
  });

  it("calculates Reports summaries from the same operational records", async () => {
    const { client, fetcher } = dependencies();
    render(<MemoryRouter><ReportsPage client={client as never} fetcher={fetcher as never} /></MemoryRouter>);

    expect(await screen.findByRole("heading", { name: "Operational reports" })).toBeInTheDocument();
    expect(await screen.findAllByText("1", { selector: ".report-metric__value" })).toHaveLength(3);
    expect(screen.getByText("Total alerts")).toBeInTheDocument();
    expect(screen.getByText("Confirmed responses")).toBeInTheDocument();
    expect(screen.getByText("820 ms")).toBeInTheDocument();
  });
});
