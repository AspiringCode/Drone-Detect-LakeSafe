import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DronesPage } from "./DronesPage";

const station = vi.hoisted(() => ({ current: null as null | { station_id: string; station_name: string; capabilities: string[] } }));
const apiRequest = vi.hoisted(() => vi.fn());
vi.mock("../hooks/useActiveStation", () => ({ useOptionalActiveStation: () => ({ station: station.current, select: vi.fn() }) }));
vi.mock("../lib/apiClient", () => ({ apiRequest }));
vi.mock("../components/AppHeader", () => ({ AppHeader: () => <header>header</header> }));

const lakes = [
  { lake_id: "test-drone-field", station_id: "st-1", org_id: null, name: "Drone Test Field", centroid_lat: 47.592, centroid_lon: -122.032 },
  { lake_id: "lake-other", station_id: "st-2", org_id: null, name: "Other Station Lake", centroid_lat: 1, centroid_lon: 1 },
];
const client = { from: () => ({ select: () => ({ order: () => Promise.resolve({ data: lakes, error: null }) }) }) } as never;
const drone = { inventory_id: "d-1", lake_id: "test-drone-field", lifecycle: "circulating", battery_percent: 90, health: "healthy", connectivity: "connected", updated_at: "", manufacturer: "Holybro", serial: "SN-1" };

const page = (setup = false) => render(<MemoryRouter><DronesPage client={client} setup={setup} /></MemoryRouter>);

describe("DronesPage", () => {
  beforeEach(() => { apiRequest.mockReset(); station.current = { station_id: "st-1", station_name: "Demo Station", capabilities: ["inventory.manage"] }; });
  afterEach(() => vi.unstubAllGlobals());

  it("is unavailable without the inventory capability", () => {
    station.current = { station_id: "st-1", station_name: "Demo Station", capabilities: ["station.read"] };
    page();
    expect(screen.getByText("Drone registry is unavailable")).toBeInTheDocument();
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it("lists drones with only this station's lakes and places a test marker at the lake centre", async () => {
    apiRequest.mockResolvedValue({ drones: [drone] });
    page();
    const select = await screen.findByLabelText("Lake for SN-1");
    expect([...select.querySelectorAll("option")].map((option) => option.textContent)).toEqual(["Not assigned", "Drone Test Field"]);
    fireEvent.click(screen.getByRole("button", { name: "Place test marker" }));
    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith("/api/stations/st-1/inventory/d-1/test-position", expect.objectContaining({ body: JSON.stringify({ lat: 47.592, lon: -122.032 }) }), client));
    fireEvent.click(screen.getByRole("button", { name: "Send patrol" }));
    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith("/api/stations/st-1/inventory/d-1/patrol", expect.objectContaining({ method: "POST" }), client));
  });

  it("keeps setup instructions off the registry", async () => {
    apiRequest.mockResolvedValue({ drones: [] });
    page();
    await screen.findByText("No real drones are registered to this station yet.");
    expect(screen.queryByLabelText("Manufacturer")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Register a drone" })).toHaveAttribute("href", "/drones/setup");
  });

  it("registers a drone and shows its ID in the connect commands", async () => {
    apiRequest.mockImplementation((path: string, init?: RequestInit) => Promise.resolve(init?.method === "POST" ? { drone_id: "new-drone" } : { drones: [] }));
    page(true);
    fireEvent.change(screen.getByLabelText("Manufacturer"), { target: { value: "Holybro" } });
    fireEvent.change(screen.getByLabelText("Serial number"), { target: { value: "SN-2" } });
    fireEvent.change(screen.getByLabelText("Public key"), { target: { value: "k".repeat(43) } });
    fireEvent.click(screen.getByRole("button", { name: "Register drone" }));
    await screen.findByText(/Drone registered/);
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));
    expect((await screen.findAllByText(/new-drone=drone\.pem/)).length).toBeGreaterThan(0);
  });

  it("connects the selected device in a fleet with multiple drones", async () => {
    vi.stubGlobal("navigator", { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
    apiRequest.mockResolvedValue({ drones: [drone, { ...drone, inventory_id: "d-2", serial: "SN-2" }] });
    page(true);
    await waitFor(() => expect(apiRequest).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Copy command" })[0]);
    await screen.findByRole("button", { name: "Copied" });
    fireEvent.change(await screen.findByLabelText("Drone to connect"), { target: { value: "d-2" } });
    expect(screen.getAllByText(/1=d-2=drone\.pem/).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "Copied" })).not.toBeInTheDocument();
  });

  it("discards an older station response after switching stations", async () => {
    let resolveOld!: (value: unknown) => void;
    apiRequest.mockImplementation((path: string) => path.includes("st-1") ? new Promise((resolve) => { resolveOld = resolve; }) : Promise.resolve({ drones: [{ ...drone, inventory_id: "d-2", serial: "SN-2", lake_id: null }] }));
    const view = page();
    station.current = { station_id: "st-2", station_name: "Second Station", capabilities: ["inventory.manage"] };
    view.rerender(<MemoryRouter><DronesPage client={client}/></MemoryRouter>);
    await screen.findByLabelText("Lake for SN-2");
    await act(async () => resolveOld({ drones: [drone] }));
    expect(screen.queryByLabelText("Lake for SN-1")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Lake for SN-2")).toBeInTheDocument();
  });
});
