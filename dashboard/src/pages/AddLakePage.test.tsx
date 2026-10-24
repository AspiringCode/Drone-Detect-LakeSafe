import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AddLakePage } from "./AddLakePage";

const request = vi.hoisted(() => vi.fn());
vi.mock("../lib/apiClient", () => ({ apiRequest: request }));
vi.mock("../auth/PrincipalProvider", () => ({ useOptionalPrincipal: () => ({ principal: { memberships: [{ station_id: "station-1", status: "active", capabilities: ["lake.create"] }] }, refresh: vi.fn() }) }));
vi.mock("../components/AppHeader", () => ({ AppHeader: () => <header/> }));
vi.mock("../components/ShorelinePreview", () => ({ ShorelinePreview: ({ onFailure }: { onFailure: () => void }) => <div role="img" aria-label="Shoreline preview"><button type="button" onClick={onFailure}>Simulate drawing failure</button></div> }));
function page() {
  render(<MemoryRouter initialEntries={["/stations/station-1/lakes/new"]}><Routes><Route path="/stations/:stationId/lakes/new" element={<AddLakePage/>}/></Routes></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("Lake name"), { target: { value: "Test lake" } });
  fireEvent.change(screen.getByLabelText("Latitude"), { target: { value: "47.6" } });
  fireEvent.change(screen.getByLabelText("Longitude"), { target: { value: "-122.1" } });
}
beforeEach(() => request.mockReset());

describe("lake shoreline review", () => {
  it("does not offer creation when the API cannot find a shoreline", async () => {
    request.mockResolvedValue({ candidates: [], data_source_status: "fallback_coverage" });
    page();
    fireEvent.click(screen.getByRole("button", { name: "Preview lake" }));
    expect(await screen.findByText(/No shoreline was found/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create lake and queue setup" })).not.toBeInTheDocument();
    expect(request).toHaveBeenCalledTimes(1);
  });

  it("shows the returned boundary and invalidates it when location details change", async () => {
    request.mockResolvedValue({ candidates: [{ name: "Test lake", shoreline: { type: "Polygon", coordinates: [[[-122.1,47.6],[-122.09,47.6],[-122.1,47.61],[-122.1,47.6]]] } }], data_source_status: "fallback_coverage" });
    page();
    fireEvent.click(screen.getByRole("button", { name: "Preview lake" }));
    expect(await screen.findByRole("img", { name: "Shoreline preview" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create lake and queue setup" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Latitude"), { target: { value: "47.61" } });
    await waitFor(() => expect(screen.queryByRole("img", { name: "Shoreline preview" })).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Preview lake" })).toBeInTheDocument();
  });

  it("withdraws creation if the returned boundary cannot be drawn", async () => {
    request.mockResolvedValue({ candidates: [{ name: "Test lake", shoreline: { type: "Polygon", coordinates: [[[-122.1,47.6],[-122.09,47.6],[-122.1,47.61],[-122.1,47.6]]] } }], data_source_status: "fallback_coverage" });
    page();
    fireEvent.click(screen.getByRole("button", { name: "Preview lake" }));
    fireEvent.click(await screen.findByRole("button", { name: "Simulate drawing failure" }));
    expect(screen.getByRole("alert")).toHaveTextContent("The shoreline could not be drawn");
    expect(screen.queryByRole("button", { name: "Create lake and queue setup" })).not.toBeInTheDocument();
    expect(request).toHaveBeenCalledTimes(1);
  });
});
