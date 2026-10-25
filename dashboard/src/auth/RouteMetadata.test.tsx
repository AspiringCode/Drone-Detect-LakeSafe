import { render, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { RouteMetadata } from "./RouteMetadata";
describe("route metadata", () => {
  it.each([["/", "Public lake notices"], ["/login", "Sign in"], ["/reset-password", "Choose a new password"], ["/lakes/lake-one", "Lake lookout"], ["/stations/s/admin", "Station administration"], ["/drones/setup", "Drone setup"]])("labels %s", async (path, title) => {
    render(<MemoryRouter initialEntries={[path]}><RouteMetadata /></MemoryRouter>);
    await waitFor(() => expect(document.title).toBe(`${title} | LakeSafe`));
    expect(document.querySelector('meta[name="description"]')?.getAttribute("content")).toBeTruthy();
  });
});
