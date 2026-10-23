import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { LakeGridPage } from "./LakeGridPage";
import { PrincipalProvider } from "../auth/PrincipalProvider";
import { ActiveStationProvider, useActiveStation } from "../hooks/useActiveStation";

vi.mock("../components/LakePreviewMap", () => ({ LakePreviewMap: () => null }));

describe("managed lake loading", () => {
  it("shows loading without claiming the station has no lakes", () => {
    const client = { from: () => ({ select: () => ({ order: () => new Promise(() => {}) }) }) };
    render(<MemoryRouter><LakeGridPage client={client as never} /></MemoryRouter>);
    expect(screen.getByRole("status")).toHaveTextContent("Loading lakes");
    expect(screen.queryByText(/No lakes are assigned/)).not.toBeInTheDocument();
  });

  it.each(["returned", "thrown"])("lets an operator retry a %s lake load error", async (kind) => {
    const order = vi.fn();
    if (kind === "returned") order.mockResolvedValueOnce({ data: null, error: { message: "unavailable" } });
    else order.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    order.mockResolvedValueOnce({ data: [{ lake_id: "lake-1", name: "Lake Washington" }], error: null });
    const client = { from: () => ({ select: () => ({ order }) }) };
    render(<MemoryRouter><LakeGridPage client={client as never} /></MemoryRouter>);
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load lakes");
    expect(screen.queryByText(/No lakes are assigned/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("link", { name: /Lake Washington/ })).toHaveAttribute("href", "/lakes/lake-1");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("ignores a superseded lake request", async () => {
    let resolveOld!: (value: unknown) => void;
    const oldClient = { from: () => ({ select: () => ({ order: () => new Promise((resolve) => { resolveOld = resolve; }) }) }) };
    const newClient = { from: () => ({ select: () => ({ order: async () => ({ data: [{ lake_id: "new", name: "Current lake" }], error: null }) }) }) };
    const { rerender } = render(<MemoryRouter><LakeGridPage client={oldClient as never} /></MemoryRouter>);
    rerender(<MemoryRouter><LakeGridPage client={newClient as never} /></MemoryRouter>);
    expect(await screen.findByRole("link", { name: /Current lake/ })).toBeInTheDocument();
    await act(async () => { resolveOld({ data: [], error: null }); });
    expect(screen.getByRole("link", { name: /Current lake/ })).toBeInTheDocument();
  });
});

it("shows every authorized lake despite a selected station and follows the opened lake's station", async () => {
  localStorage.setItem("lakesafe-active-station", "station-a");
  const lakes = [
    { lake_id: "a", station_id: "station-a", name: "Lake A" },
    { lake_id: "b", station_id: "station-b", name: "Lake B" },
    { lake_id: "c", station_id: "station-c", name: "Lake C" },
  ];
  const client = { auth: {
    getSession: vi.fn().mockResolvedValue({ data: { session: { access_token: "test" } } }),
    onAuthStateChange: () => ({ data: { subscription: { unsubscribe: vi.fn() } } }),
  }, from: () => ({ select: () => ({ order: async () => ({ data: lakes, error: null }) }) }) };
  const principal = { memberships: lakes.map(lake => ({ station_id: lake.station_id, station_name: lake.name, status: "active", capabilities: [], roles: [] })) };
  function Selection() { return <output aria-label="Selected station">{useActiveStation().station?.station_id}</output>; }
  render(<MemoryRouter><PrincipalProvider client={client as never} request={vi.fn().mockResolvedValue(principal)}><ActiveStationProvider><LakeGridPage client={client as never}/><Selection/></ActiveStationProvider></PrincipalProvider></MemoryRouter>);
  for (const lake of lakes) expect(await screen.findByRole("link", { name: lake.name })).toHaveAttribute("href", `/lakes/${lake.lake_id}`);
  expect(screen.queryByRole("combobox", { name: "Active station" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("link", { name: "Lake B" }));
  expect(screen.getByLabelText("Selected station")).toHaveTextContent("station-b");
  localStorage.removeItem("lakesafe-active-station");
});
