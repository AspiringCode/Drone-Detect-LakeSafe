import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AutonomyControls } from "./AutonomyControls";
import { FleetInventoryPanel } from "./FleetInventoryPanel";
import type { FleetDrone } from "../lib/types";
import { applyReconcileStatus } from "../lib/fleetData";

const fleet: FleetDrone[] = [{
  inventoryId: "sim-1", source: "simulated", lifecycle: "available",
  batteryPercent: 93, health: "healthy", connectivity: "online",
  desiredStateVersion: 4, acknowledgedStateVersion: 3,
}];

describe("autonomous fleet controls", () => {
  it("shows desired and acknowledged state separately", () => {
    render(<FleetInventoryPanel drones={fleet} />);
    expect(screen.getByText("Update pending")).toBeVisible();
    expect(screen.getByText("Desired 4")).toBeVisible();
    expect(screen.getByText("Acknowledged 3")).toBeVisible();
  });

  it("does not render circulation controls for a viewer", () => {
    render(<AutonomyControls capabilities={["station.read"]} drones={fleet} onRequest={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /add to circulation/i })).not.toBeInTheDocument();
  });

  it("sends only eligibility and reason for a simulated drone", () => {
    const onRequest = vi.fn();
    render(<AutonomyControls capabilities={["autonomy.manage"]} drones={fleet} onRequest={onRequest} />);
    fireEvent.click(screen.getByRole("button", { name: /add sim-1 to circulation/i }));
    expect(onRequest).toHaveBeenCalledWith("sim-1", { eligible: true, reason: "coverage" });
  });

  it("keeps the acknowledged lifecycle while a desired update is pending", () => {
    const updated = applyReconcileStatus(fleet, "sim-1", { reconciliationId: "r1", desiredStateVersion: 5, acknowledgedStateVersion: 3 });
    expect(updated[0].lifecycle).toBe("available");
    expect(updated[0].desiredStateVersion).toBe(5);
    expect(updated[0].acknowledgedStateVersion).toBe(3);
  });
});
