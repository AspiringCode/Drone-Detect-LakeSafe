import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AutonomyControls } from "./AutonomyControls";
import { FleetInventoryPanel } from "./FleetInventoryPanel";
import type { FleetDrone } from "../lib/types";

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
});
