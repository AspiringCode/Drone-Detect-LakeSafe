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

  it("labels each row's source and shortens real device UUIDs", () => {
    const id = "13adf59c-ef47-43b8-9024-4fefef66b7b5";
    render(<DroneRoster drones={[{ ...drones[0], drone_id: id, source: "real" }, drones[1]]} />);
    expect(screen.getByText("13adf59c…")).toHaveAttribute("title", id);
    expect(screen.getByText("real")).toBeTruthy();
    expect(screen.getByText("simulated")).toBeTruthy();
  });

  it("lists registered real drones by serial, including ones not yet heartbeating", () => {
    const id = "13adf59c-ef47-43b8-9024-4fefef66b7b5";
    render(<DroneRoster drones={[{ ...drones[0], drone_id: id, source: "real" }]} registered={[
      { inventory_id: id, manufacturer: "Holybro", serial: "SN-LIVE", last_heartbeat_at: "2026-10-24T18:00:00Z" },
      { inventory_id: "waiting-id", manufacturer: "Holybro", serial: "SN-NEW", last_heartbeat_at: null },
    ]} />);
    expect(screen.getByText("SN-LIVE")).toHaveAttribute("title", id);
    expect(screen.getByText("SN-NEW")).toBeTruthy();
    expect(screen.getByText("awaiting heartbeat")).toBeTruthy();
  });

  it("shortens simulated lake drone IDs and keeps the full ID on hover", () => {
    render(<DroneRoster drones={[{ ...drones[0], drone_id: "lake-sammamish-d0" }]} />);
    expect(screen.getByText("Sim 1")).toHaveAttribute("title", "lake-sammamish-d0");
  });

  it("explains how to get drones when the lake has none", () => {
    render(<DroneRoster drones={[]} />);
    expect(screen.getByText(/Start a simulation, or assign a registered drone/)).toBeTruthy();
  });

  it("exposes battery charge as an accessible visual meter", () => {
    render(<DroneRoster drones={drones} />);
    const meters = screen.getAllByRole("progressbar", { name: /battery/i });
    expect(meters).toHaveLength(2);
    expect(meters[0]).toHaveAttribute("aria-valuenow", "82");
    expect(meters[1]).toHaveAttribute("aria-valuenow", "20");
  });
});
