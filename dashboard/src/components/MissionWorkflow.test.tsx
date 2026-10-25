import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { MissionWorkflow } from "./MissionWorkflow";

const request = vi.hoisted(() => vi.fn());
vi.mock("../lib/apiClient", () => ({ apiRequest: request }));
const drone = { inventory_id: "d-1", lake_id: "lake-1" };
const client = {} as never;
beforeEach(() => { request.mockReset(); });
it("requires an explicit preview before queueing the reviewed launch and zone", async () => {
  request.mockImplementation((path: string) => Promise.resolve(path.endsWith("/patrol-zones") ? { zones: [{ zone_id: "z1", radius_m: 40, is_proxy: false }], assigned_zone_id: "z1" } : path.endsWith("/mission-preview") ? { zone_id: "z1", home: { lat: 47.59, lon: -122.03 }, altitude_m: 30, waypoint_count: 19, mission_hash: "a".repeat(64), route: [] } : { command_id: "command-1", status: "queued" }));
  const queued = vi.fn();
  render(<MissionWorkflow drone={drone} stationId="s-1" client={client} send onQueued={queued}/>);
  fireEvent.change(await screen.findByLabelText("Home latitude"), { target: { value: "47.59" } });
  fireEvent.change(screen.getByLabelText("Home longitude"), { target: { value: "-122.03" } });
  expect(screen.queryByRole("button", { name: "Queue reviewed patrol" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Preview mission" }));
  fireEvent.click(await screen.findByRole("button", { name: "Queue reviewed patrol" }));
  await waitFor(() => expect(queued).toHaveBeenCalled());
  expect(request).toHaveBeenCalledWith("/api/stations/s-1/inventory/d-1/patrol", expect.objectContaining({ body: JSON.stringify({ zone_id: "z1", home_lat: 47.59, home_lon: -122.03, altitude_m: 30, reviewed_hash: "a".repeat(64) }) }), client);
});
it("invalidates a preview when launch details change", async () => {
  request.mockImplementation((path: string) => Promise.resolve(path.endsWith("/patrol-zones") ? { zones: [{ zone_id: "z1", radius_m: 40 }] } : { zone_id: "z1", home: { lat: 47.59, lon: -122.03 }, altitude_m: 30, waypoint_count: 19, mission_hash: "a".repeat(64), route: [] }));
  render(<MissionWorkflow drone={drone} stationId="s-1" client={client} send/>);
  fireEvent.change(await screen.findByLabelText("Home latitude"), { target: { value: "47.59" } });
  fireEvent.change(screen.getByLabelText("Home longitude"), { target: { value: "-122.03" } });
  fireEvent.click(screen.getByRole("button", { name: "Preview mission" }));
  await screen.findByRole("button", { name: "Queue reviewed patrol" });
  fireEvent.change(screen.getByLabelText("Altitude (m)"), { target: { value: "40" } });
  expect(screen.queryByRole("button", { name: "Queue reviewed patrol" })).not.toBeInTheDocument();
});
it("reloads zones after the drone changes lakes", async () => {
  request.mockResolvedValueOnce({ zones: [{ zone_id: "old-zone", radius_m: 20 }] }).mockResolvedValue({ zones: [{ zone_id: "new-zone", radius_m: 20 }] });
  const view = render(<MissionWorkflow drone={drone} stationId="s-1" client={client} send/>);
  await screen.findByRole("option", { name: /old-zone/ });
  view.rerender(<MissionWorkflow drone={{ ...drone, lake_id: "lake-2" }} stationId="s-1" client={client} send/>);
  expect(await screen.findByRole("option", { name: /new-zone/ })).toBeInTheDocument();
  expect(screen.queryByRole("option", { name: /old-zone/ })).not.toBeInTheDocument();
});
