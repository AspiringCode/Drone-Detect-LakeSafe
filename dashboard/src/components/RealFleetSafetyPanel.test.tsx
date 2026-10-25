import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RealFleetSafetyPanel } from "./RealFleetSafetyPanel";

const paused = {
  source: "real" as const,
  realAutonomy: "paused" as const,
  heartbeatAgeSeconds: 7,
  eligible: true,
  desiredStateVersion: 5,
  acknowledgedStateVersion: 5,
};

describe("real fleet safety controls", () => {
  it("requires safety-supervisor capability for real fleet changes", () => {
    render(<RealFleetSafetyPanel capabilities={["inventory.manage"]} status={paused} onSetAutonomy={vi.fn()} onRequestSafeReturn={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /enable real autonomy/i })).not.toBeInTheDocument();
  });

  it("labels desired state as pending until device acknowledgement", () => {
    render(<RealFleetSafetyPanel capabilities={["autonomy.manage"]} status={{ ...paused, realAutonomy: "pending_ack", desiredStateVersion: 6, acknowledgedStateVersion: 5 }} onSetAutonomy={vi.fn()} onRequestSafeReturn={vi.fn()} />);
    expect(screen.getByText(/waiting for device acknowledgement\. desired policy is not active yet/i)).toBeVisible();
  });

  it("sends only an enabled policy and nonempty reason", () => {
    const onSetAutonomy = vi.fn();
    render(<RealFleetSafetyPanel capabilities={["fleet_safety.manage"]} status={paused} onSetAutonomy={onSetAutonomy} onRequestSafeReturn={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /enable real autonomy/i }));
    expect(screen.getByRole("alert")).toHaveTextContent(/reason is required/i);
    fireEvent.change(screen.getByLabelText(/safety reason/i), { target: { value: "Shift handoff confirmed" } });
    fireEvent.click(screen.getByRole("button", { name: /enable real autonomy/i }));
    expect(onSetAutonomy).toHaveBeenCalledWith(true, "Shift handoff confirmed");
    expect(onSetAutonomy.mock.calls[0][0]).not.toHaveProperty("coordinates");
  });

  it("renders degraded gateway state without individual steering controls", () => {
    render(<RealFleetSafetyPanel capabilities={["autonomy.manage"]} status={{ ...paused, realAutonomy: "gateway_unavailable", eligible: false, heartbeatAgeSeconds: 23 }} onSetAutonomy={vi.fn()} onRequestSafeReturn={vi.fn()} />);
    expect(screen.getByText(/gateway is unavailable/i)).toBeVisible();
    expect(screen.getByText(/23 seconds ago/i)).toBeVisible();
    expect(screen.queryByLabelText(/coordinate|heading|altitude|velocity|waypoint|route/i)).not.toBeInTheDocument();
  });
});
