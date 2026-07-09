import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DroneRoster } from "./DroneRoster";
import type { Drone } from "../lib/types";

const drones: Drone[] = [
  {
    drone_id: "d1",
    pos: { lat: 47.58, lon: -122.09 },
    battery: 0.82,
    status: "patrolling",
    assigned_zone: "z1-2",
    source: "simulated",
  },
  {
    drone_id: "d2",
    pos: { lat: 47.582, lon: -122.088 },
    battery: 0.2,
    status: "returning",
    assigned_zone: null,
    source: "simulated",
  },
];

describe("DroneRoster", () => {
  it("renders a row per drone with id, status, battery percentage, and zone", () => {
    render(<DroneRoster drones={drones} />);
    expect(screen.getByText("d1")).toBeTruthy();
    expect(screen.getByText("patrolling")).toBeTruthy();
    expect(screen.getByText("82%")).toBeTruthy();
    expect(screen.getByText("z1-2")).toBeTruthy();
  });

  it("shows a dash when a drone has no assigned zone", () => {
    render(<DroneRoster drones={drones} />);
    expect(screen.getByText("d2")).toBeTruthy();
    expect(screen.getByText("20%")).toBeTruthy();
    expect(screen.getAllByText("-").length).toBeGreaterThan(0);
  });
});
