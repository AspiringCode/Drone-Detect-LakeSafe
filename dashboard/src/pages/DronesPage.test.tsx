import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DronesPage } from "./DronesPage";

const station = vi.hoisted(() => ({ current: null as null | { station_id: string; station_name: string; capabilities: string[] }, select: vi.fn() }));
const apiRequest = vi.hoisted(() => vi.fn());
vi.mock("../hooks/useActiveStation", () => ({ useOptionalActiveStation: () => ({ station: station.current, select: station.select }) }));
vi.mock("../auth/PrincipalProvider", () => ({ useOptionalPrincipal: () => ({ principal: { memberships: [
  { station_id: "st-1", station_name: "Demo Station", status: "active" },
  { station_id: "st-2", station_name: "Second Station", status: "active" },
  { station_id: "st-3", station_name: "Inactive Station", status: "revoked" },
] } }) }));
vi.mock("../lib/apiClient", () => ({ apiRequest }));
vi.mock("../components/AppHeader", () => ({ AppHeader: ({ showStationPicker }: { showStationPicker?: boolean }) => <header data-testid="app-header">header{showStationPicker && <select aria-label="Active station"/>}</header> }));

const lakes = [
  { lake_id: "test-drone-field", station_id: "st-1", org_id: null, name: "Drone Test Field", centroid_lat: 47.592, centroid_lon: -122.032 },
  { lake_id: "lake-other", station_id: "st-2", org_id: null, name: "Other Station Lake", centroid_lat: 1, centroid_lon: 1 },
];
const client = { from: () => ({ select: () => ({ order: () => Promise.resolve({ data: lakes, error: null }) }) }) } as never;
const drone = { inventory_id: "d-1", lake_id: "test-drone-field", lifecycle: "circulating", battery_percent: 90, health: "healthy", connectivity: "connected", updated_at: "", manufacturer: "Holybro", serial: "SN-1" };

const page = (setup = false) => render(<MemoryRouter><DronesPage client={client} setup={setup} /></MemoryRouter>);

describe("DronesPage", () => {
  beforeEach(() => { apiRequest.mockReset(); station.select.mockReset(); station.current = { station_id: "st-1", station_name: "Demo Station", capabilities: ["inventory.manage"] }; });
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
    expect(await screen.findByRole("dialog", { name: "Review patrol mission" })).toBeInTheDocument();
    expect(apiRequest).not.toHaveBeenCalledWith("/api/stations/st-1/inventory/d-1/patrol", expect.anything(), client);
    fireEvent.click(screen.getByRole("button", { name: "Close mission review" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("keeps setup instructions off the registry", async () => {
    apiRequest.mockResolvedValue({ drones: [] });
    page();
    await screen.findByText("No real drones are registered to this station yet.");
    expect(screen.queryByLabelText("Manufacturer")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Register a drone" })).toHaveAttribute("href", "/drones/setup");
  });

  it("puts the station control under the page title and links Add drone to setup", async () => {
    apiRequest.mockResolvedValue({ drones: [] });
    page();
    const picker = screen.getByRole("combobox", { name: "Active station" });
    expect(picker.closest(".page-heading")).toHaveTextContent("Drones");
    expect(screen.getByTestId("app-header").querySelector("select")).toBeNull();
    expect([...picker.querySelectorAll("option")].map((option) => option.textContent)).toEqual(["Demo Station", "Second Station"]);
    fireEvent.change(picker, { target: { value: "st-2" } });
    expect(station.select).toHaveBeenCalledWith("st-2");
    expect(screen.getByRole("link", { name: "Add drone" })).toHaveAttribute("href", "/drones/setup");
    expect(screen.queryByRole("link", { name: "Open setup guide" })).not.toBeInTheDocument();
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

  it("moves a newly registered drone to lake assignment and highlights it", async () => {
    apiRequest.mockImplementation((path: string, init?: RequestInit) => Promise.resolve(init?.method === "POST" ? { drone_id: "new-drone" } : { drones: [{ ...drone, inventory_id: "new-drone", lake_id: null }] }));
    page(true);
    fireEvent.change(screen.getByLabelText("Manufacturer"), { target: { value: "Holybro" } });
    fireEvent.change(screen.getByLabelText("Serial number"), { target: { value: "SN-1" } });
    fireEvent.change(screen.getByLabelText("Public key"), { target: { value: "k".repeat(43) } });
    fireEvent.click(screen.getByRole("button", { name: "Register drone" }));
    expect(await screen.findByRole("button", { name: "Registering…" })).toBeDisabled();
    expect(await screen.findByLabelText("Lake for SN-1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Assign lake/ })).toHaveAttribute("aria-current", "step");
    expect(screen.getByText("New")).toBeInTheDocument();
  });

  it("shows awaiting first heartbeat instead of default telemetry", async () => {
    apiRequest.mockResolvedValue({ drones: [{ ...drone, last_heartbeat_at: null }, { ...drone, inventory_id: "d-2", serial: "SN-2", last_heartbeat_at: new Date().toISOString() }] });
    page();
    expect(await screen.findByText(/Awaiting first heartbeat/)).toBeInTheDocument();
    expect(screen.getByText(/connected · healthy · 90% · last heartbeat just now/)).toBeInTheDocument();
  });

  it("keeps the registry visible when an action fails and confirms before retiring", async () => {
    apiRequest.mockImplementation((path: string) => path.endsWith("/test-position") ? Promise.reject(new Error("The drone's credential is not active")) : Promise.resolve({ drones: [drone] }));
    page();
    fireEvent.click(await screen.findByRole("button", { name: "Place test marker" }));
    expect(await screen.findByText("The drone's credential is not active")).toBeInTheDocument();
    expect(screen.getByLabelText("Lake for SN-1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retire" }));
    expect(screen.getByRole("dialog", { name: "Retire drone" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(apiRequest).not.toHaveBeenCalledWith(expect.stringContaining("/retire"), expect.anything(), client);
  });

  it("refreshes a newly connected drone without navigating away", async () => {
    let connected = false;
    apiRequest.mockImplementation(() => Promise.resolve({ drones: [{ ...drone, last_heartbeat_at: connected ? new Date().toISOString() : null }] }));
    page();
    await screen.findByText(/Awaiting first heartbeat/);
    connected = true;
    fireEvent.click(screen.getByRole("button", { name: "Refresh fleet" }));
    expect(await screen.findByText(/connected · healthy · 90%/)).toBeInTheDocument();
  });

  it("downloads a Mission Planner file for a chosen zone and explicit home", async () => {
    const createObjectURL = vi.fn().mockReturnValue("blob:mission");
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL: vi.fn() });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    apiRequest.mockImplementation((path: string) => Promise.resolve(path.endsWith("/patrol-zones") ? { zones: [{ zone_id: "z0", radius_m: 40, is_proxy: false }] } : path.endsWith("/mission") ? "QGC WPL 110\n" : { drones: [drone] }));
    page();
    const details = (await screen.findByText("Download mission")).closest("details")!;
    details.open = true;
    fireEvent(details, new Event("toggle"));
    fireEvent.change(await screen.findByLabelText("Home latitude"), { target: { value: "47.5915" } });
    fireEvent.change(screen.getByLabelText("Home longitude"), { target: { value: "-122.033" } });
    fireEvent.click(screen.getByRole("button", { name: "Download .waypoints" }));
    await waitFor(() => expect(click).toHaveBeenCalled());
    expect(apiRequest).toHaveBeenCalledWith("/api/stations/st-1/inventory/d-1/mission", expect.objectContaining({ body: JSON.stringify({ zone_id: "z0", home_lat: 47.5915, home_lon: -122.033, altitude_m: 30 }) }), client);
    click.mockRestore();
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
