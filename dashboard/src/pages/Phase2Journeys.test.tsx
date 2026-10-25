import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { PrincipalProvider } from "../auth/PrincipalProvider";
import { InvitationAcceptPage } from "./InvitationAcceptPage";
import { ReviewConsolePage } from "./ReviewConsolePage";
import { StationAccessPage } from "./StationAccessPage";
import { StationAdminPage } from "./StationAdminPage";

const request = vi.fn().mockResolvedValue({ station_id: "station-1", status: "active" });

vi.mock("../lib/apiClient", () => ({ apiRequest: (...args: unknown[]) => request(...args) }));

function sessionClient() {
  return {
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token" } } }),
      onAuthStateChange: () => ({ data: { subscription: { unsubscribe() {} } } }),
    },
  };
}

function Location() { return <p data-testid="location">{useLocation().pathname}</p>; }

function workspace(principal: Record<string, unknown>, page: ReactNode, entry = "/station-access") {
  return render(<PrincipalProvider client={sessionClient() as never} request={async () => principal as never}>
    <MemoryRouter initialEntries={[entry]}><Routes>
      <Route path="/station-access" element={page} />
      <Route path="/stations/:stationId/admin" element={page} />
      <Route path="/internal/reviews" element={page} />
    </Routes></MemoryRouter>
  </PrincipalProvider>);
}

const civilian = { user_id: "civilian", email: "civilian@example.com", aal: "aal1", account_class: "civilian", verification_status: "not_started", reviewer: false, memberships: [] };
const verifiedUnassigned = { ...civilian, user_id: "officer", aal: "aal2", account_class: "officer", verification_status: "verified" };

describe("Phase 2 invited-member journey", () => {
  it("switches station administration and loads the selected station's members", async () => {
    request.mockImplementation(async (path: string) => path.endsWith("/members") ? {members:[]} : {requests:[]});
    workspace({ ...verifiedUnassigned, memberships: ["one","two"].map(id => ({ station_id:id,station_name:`Station ${id}`,status:"active",roles:["station_admin"],capabilities:["member.manage","lake.create"] })) }, <StationAdminPage/>, "/stations/one/admin");
    expect(await screen.findByRole("heading",{name:"Station one"})).toBeVisible();
    fireEvent.change(screen.getByRole("combobox",{name:"Active station"}),{target:{value:"two"}});
    expect(await screen.findByRole("heading",{name:"Station two"})).toBeVisible();
    expect(request).toHaveBeenCalledWith("/api/stations/two/members",{},expect.anything());
  });
  it("refreshes the principal and returns an invited viewer to the lakes workspace", async () => {
    render(<PrincipalProvider client={sessionClient() as never} request={async () => ({ user_id: "officer-1", email: "officer@example.gov", aal: "aal2", account_class: "officer", verification_status: "verified", reviewer: false, memberships: [] }) as never}>
      <MemoryRouter initialEntries={["/invitations/accept?token=single-use"]}><Routes>
        <Route path="/invitations/accept" element={<InvitationAcceptPage />} />
        <Route path="/lakes" element={<Location />} />
      </Routes></MemoryRouter>
    </PrincipalProvider>);

    fireEvent.click(await screen.findByRole("button", { name: /accept invitation/i }));

    expect(await screen.findByTestId("location")).toHaveTextContent("/lakes");
    expect(request).toHaveBeenCalledWith("/api/invitations/accept", expect.objectContaining({ method: "POST" }), expect.anything());
  });
});

describe("Phase 2 persona controls", () => {
  it("keeps the civilian station page limited to the verification route", async () => {
    workspace(civilian, <StationAccessPage />);
    expect(await screen.findByRole("heading", { name: /before joining another station/i })).toBeVisible();
    expect(screen.getByRole("link", { name: /review access requirements/i })).toHaveAttribute("href", "/verify-affiliation");
    expect(screen.queryByRole("button", { name: /send for review/i })).not.toBeInTheDocument();
  });

  it("gives a verified unassigned officer only station discovery and request controls", async () => {
    workspace(verifiedUnassigned, <StationAccessPage />);
    expect(await screen.findByRole("heading", { name: /find an existing station/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /search stations/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /send for review/i })).toBeVisible();
  });

  it("shows station administration controls only for an active station administrator", async () => {
    request.mockImplementation(async (path: string) => path.endsWith("/members") ? {members:[]} : {requests:[]});
    workspace({ ...verifiedUnassigned, memberships: [{ station_id: "station-1", station_name: "Station One", status: "active", roles: ["station_admin"], capabilities: ["member.manage", "lake.create"] }] }, <StationAdminPage />, "/stations/station-1/admin");
    expect((await screen.findAllByRole("heading", { name: "Station One" }))[0].tagName).toBe("H1");
    expect(screen.getByRole("link", { name: /add lake/i })).toHaveAttribute("href", "/stations/station-1/lakes/new");
    expect(screen.getByRole("button", { name: /create invitation/i })).toBeVisible();
  });

  it("shows the review route only to a LakeSafe reviewer", async () => {
    request.mockResolvedValueOnce({ requests: [{ station_request_id: "request-1", requested_name: "LakeSafe Station" }] });
    workspace({ ...verifiedUnassigned, reviewer: true }, <ReviewConsolePage />, "/internal/reviews");
    expect(await screen.findByRole("heading", { name: "LakeSafe Station" })).toBeVisible();
    expect(screen.getByRole("button", { name: /approve station/i })).toBeVisible();
  });
});
