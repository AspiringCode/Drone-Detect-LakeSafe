import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AppHeader } from "./AppHeader";
import { PrincipalProvider } from "../auth/PrincipalProvider";
import { ActiveStationProvider } from "../hooks/useActiveStation";

describe("AppHeader", () => {
  it.each([
    { status: "active", capabilities: ["member.manage"], visible: true },
    { status: "active", capabilities: ["station.read"], visible: false },
    { status: "suspended", capabilities: ["member.manage"], visible: false },
  ])("limits station administration navigation to an active capable membership: $status $capabilities", async ({ status, capabilities, visible }) => {
    const fakeClient = { ...client(), auth: { ...client().auth,
      getSession: vi.fn().mockResolvedValue({ data: { session: { access_token: "test" } } }),
      onAuthStateChange: () => ({ data: { subscription: { unsubscribe: vi.fn() } } }),
    } };
    const request = vi.fn().mockResolvedValue({ memberships: [{ station_id: "station-1", station_name: "Station one", status, capabilities, roles: [] }] });
    render(<MemoryRouter><PrincipalProvider client={fakeClient as never} request={request}><ActiveStationProvider><AppHeader active="lakes" client={fakeClient as never} /></ActiveStationProvider></PrincipalProvider></MemoryRouter>);
    await waitFor(() => expect(request).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByRole("combobox", { name: /active station/i })).toHaveDisplayValue(status === "active" ? "Station one" : "No active station"));
    fireEvent.click(screen.getByRole("button", { name: /open account menu/i }));
    if (visible) expect(screen.getByRole("link", { name: "Station administration" })).toHaveAttribute("href", "/stations/station-1/admin");
    else expect(screen.queryByRole("link", { name: "Station administration" })).not.toBeInTheDocument();
  });

  function client() {
    return {
      auth: {
        getUser: vi.fn().mockResolvedValue({ data: { user: { email: "operator@example.com", user_metadata: { display_name: "Lake Operator" } } }, error: null }),
        signOut: vi.fn().mockResolvedValue({ error: null }),
      },
      from: vi.fn(() => ({
        select: vi.fn().mockResolvedValue({ data: [{ org_id: "org-demo", name: "LakeSafe Demo Station" }], error: null }),
      })),
    };
  }

  it("shows workspace navigation, a station selector, and an account menu", async () => {
    const fakeClient = client();
    render(
      <MemoryRouter>
        <AppHeader active="operations" client={fakeClient as never} />
      </MemoryRouter>,
    );

    expect(screen.getByText("LakeSafe")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Lakes" })).toHaveAttribute("href", "/lakes");
    expect(screen.getByRole("link", { name: "Operations" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Alerts" })).toHaveAttribute("href", "/alerts");
    expect(screen.getByRole("link", { name: "Reports" })).toHaveAttribute("href", "/reports");
    expect(await screen.findByRole("combobox", { name: /active station/i })).toHaveDisplayValue("No active station");

    fireEvent.click(screen.getByRole("button", { name: /open account menu/i }));
    expect(screen.getByRole("link", { name: /profile settings/i })).toHaveAttribute("href", "/profile");
    expect(screen.getByRole("button", { name: /sign out/i })).toBeInTheDocument();
  });

  it("signs the operator out and returns to login", async () => {
    const fakeClient = client();
    render(
      <MemoryRouter initialEntries={["/lakes"]}>
        <Routes>
          <Route path="/lakes" element={<AppHeader active="lakes" client={fakeClient as never} />} />
          <Route path="/login" element={<p>Signed out</p>} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /open account menu/i }));
    fireEvent.click(screen.getByRole("button", { name: /sign out/i }));

    await waitFor(() => expect(fakeClient.auth.signOut).toHaveBeenCalledOnce());
    expect(await screen.findByText("Signed out")).toBeInTheDocument();
  });
});
