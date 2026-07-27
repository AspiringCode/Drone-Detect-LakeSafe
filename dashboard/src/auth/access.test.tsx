import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { PrincipalProvider } from "./PrincipalProvider";
import { RequireCapability } from "./RequireCapability";
import { ActiveStationProvider, useActiveStation } from "../hooks/useActiveStation";
import type { Principal } from "../lib/types";

const civilian: Principal = { user_id: "u", email: "civilian@example.com", aal: "aal1", account_class: "civilian", verification_status: "not_started", reviewer: false, memberships: [] };
const officer: Principal = { ...civilian, aal: "aal2", account_class: "officer", memberships: [{ station_id: "station-1", station_name: "First", status: "active", roles: ["station_admin"], capabilities: ["lake.create"] }] };
function client() { return { auth: { getSession: async () => ({ data: { session: { access_token: "token" } } }), onAuthStateChange: () => ({ data: { subscription: { unsubscribe() {} } } }) } }; }
function app(principal: Principal, path = "/lakes") { const request = async () => principal; return render(<PrincipalProvider client={client() as never} request={request as never}><ActiveStationProvider><MemoryRouter initialEntries={[path]}><Routes><Route path="/lakes" element={<p>Civilian map</p>} /><Route element={<RequireCapability capability="lake.create" />}><Route path="/manage" element={<p>Manage lake</p>} /></Route></Routes></MemoryRouter></ActiveStationProvider></PrincipalProvider>); }
describe("access foundation", () => {
  it("keeps civilians in the usable application without a membership", async () => { app(civilian); expect(await screen.findByText("Civilian map")).toBeInTheDocument(); });
  it("redirects a user without the required AAL2 capability", async () => { app(civilian, "/manage"); expect(await screen.findByText("Civilian map")).toBeInTheDocument(); });
  it("allows an active AAL2 membership capability", async () => { app(officer, "/manage"); expect(await screen.findByText("Manage lake")).toBeInTheDocument(); });
});
