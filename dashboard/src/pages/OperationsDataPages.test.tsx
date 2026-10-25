import { fireEvent, render, screen } from "@testing-library/react";
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
      getSession: vi.fn().mockResolvedValue({ data: { session: { access_token: "operator-token" } } }),
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
    expect(await screen.findByText("Lake Sammamish", { selector: ".alert-record p" })).toBeInTheDocument();
    expect(screen.getByText("drone-2")).toBeInTheDocument();
    expect(screen.getByText("Confirmed")).toBeInTheDocument();
    expect(fetcher).toHaveBeenCalledWith(expect.stringContaining("/api/lakes/lake-sammamish/alerts"), { headers: { Authorization: "Bearer operator-token" } });
  });

  it("reports an alert service failure instead of showing an empty list", async () => {
    const { client, fetcher } = dependencies();
    fetcher.mockResolvedValue({ ok: false, status: 401, json: async () => ({}) });
    render(<MemoryRouter><AlertsPage client={client as never} fetcher={fetcher as never} /></MemoryRouter>);
    expect(await screen.findByText("Could not load operational alerts.")).toBeInTheDocument();
  });

  it("marks a lake without a runtime as unavailable rather than claiming healthy coverage", async () => {
    const { client, fetcher } = dependencies();
    fetcher.mockResolvedValue({ ok: false, status: 404, json: async () => ({}) });
    render(<MemoryRouter><ReportsPage client={client as never} fetcher={fetcher as never}/></MemoryRouter>);
    expect(await screen.findByText("Current records unavailable")).toBeInTheDocument();
    expect(screen.queryByText("Current records available")).not.toBeInTheDocument();
    expect(screen.getByText(/does not confirm patrol coverage/i)).toBeInTheDocument();
  });

  it("calculates Reports summaries from the same operational records", async () => {
    const { client, fetcher } = dependencies();
    render(<MemoryRouter><ReportsPage client={client as never} fetcher={fetcher as never} /></MemoryRouter>);

    expect(await screen.findByRole("heading", { name: "Operational reports" })).toBeInTheDocument();
    expect(await screen.findAllByText("1", { selector: ".report-metric__value" })).toHaveLength(3);
    expect(screen.getByText("Total alerts")).toBeInTheDocument();
    expect(screen.getByText("Confirmed detections")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Refresh reports" })).toBeVisible();
    expect(screen.getByText("820 ms")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Incident records" })).toHaveTextContent("Lake Sammamish");
    expect(screen.getByText(/current available records, not a historical reporting period/i)).toBeInTheDocument();
  });

  it("retries reporting failures without replacing them with zero totals", async () => {
    const { client, fetcher } = dependencies();
    fetcher.mockRejectedValueOnce(new TypeError("offline"));
    render(<MemoryRouter><ReportsPage client={client as never} fetcher={fetcher as never} /></MemoryRouter>);
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not calculate operational reports.");
    expect(screen.queryByText("Total alerts")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("820 ms")).toBeInTheDocument();
  });

  it("filters incident records by source without changing the underlying record count", async () => {
    const { client, fetcher } = dependencies();
    render(<MemoryRouter><ReportsPage client={client as never} fetcher={fetcher as never} /></MemoryRouter>);
    await screen.findByText("820 ms");
    fireEvent.change(screen.getByLabelText("Source"), { target: { value: "real" } });
    expect(screen.queryByRole("table", { name: "Incident records" })).not.toBeInTheDocument();
    expect(screen.getByText("No records match these filters.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Source"), { target: { value: "simulated" } });
    expect(screen.getByRole("table", { name: "Incident records" })).toHaveTextContent("thermal");
  });
});
