import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { LoginPage } from "./LoginPage";
import { VerifyOtpPage } from "./VerifyOtpPage";
import { hasLakeCapability } from "./LakeLiveView";
import { PrincipalProvider } from "../auth/PrincipalProvider";
import { RequireCapability } from "../auth/RequireCapability";
import { AppHeader } from "../components/AppHeader";
import type { Principal } from "../lib/types";

const ordinary = { user_id: "operator", aal: "aal1", account_class: "officer", memberships: [{ station_id: "station", status: "active", capabilities: ["station.read"] }] } as Principal;
const judge = { ...ordinary, judge_demo_access: true } as Principal;
function client() {
  return { auth: {
    signInWithPassword: vi.fn().mockResolvedValue({ data: { session: { access_token: "token" } }, error: null }),
    getSession: vi.fn().mockResolvedValue({ data: { session: { access_token: "token" } } }),
    onAuthStateChange: () => ({ data: { subscription: { unsubscribe: vi.fn() } } }),
    mfa: {
      getAuthenticatorAssuranceLevel: vi.fn().mockResolvedValue({ data: { currentLevel: "aal1" } }),
      listFactors: vi.fn().mockResolvedValue({ data: { totp: [] }, error: null }),
      enroll: vi.fn().mockResolvedValue({ data: { id: "factor", totp: { qr_code: "data:image/svg+xml,test", secret: "SETUP" } }, error: null }),
    },
  } };
}
function login(fake: ReturnType<typeof client>, request: unknown) {
  render(<MemoryRouter initialEntries={["/login"]}><Routes><Route path="/login" element={<LoginPage client={fake as never} request={request as never} />} /><Route path="/lakes" element={<p>Lake workspace</p>} /><Route path="/verify-2fa" element={<p>OTP required</p>} /></Routes></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "operator@example.com" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
}

describe("server-approved judge access", () => {
  it("allows an approved AAL1 judge after checking the authenticated principal", async () => {
    const fake = client(); const request = vi.fn().mockResolvedValue(judge);
    login(fake, request);
    expect(await screen.findByText("Lake workspace")).toBeVisible();
    expect(request).toHaveBeenCalledWith("/api/me", undefined, fake);
  });
  it("keeps ordinary AAL1 operators on the OTP path", async () => {
    const fake = client(); login(fake, vi.fn().mockResolvedValue(ordinary));
    expect(await screen.findByText("OTP required")).toBeVisible();
  });
  it("keeps ordinary AAL2 operators on the workspace path", async () => {
    const fake = client(); fake.auth.mfa.getAuthenticatorAssuranceLevel.mockResolvedValue({ data: { currentLevel: "aal2" } });
    login(fake, vi.fn().mockResolvedValue({ ...ordinary, aal: "aal2" }));
    expect(await screen.findByText("Lake workspace")).toBeVisible();
  });
  it("shows an API outage without falling back to OTP or workspace navigation", async () => {
    login(client(), vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not check account access");
    expect(screen.queryByText("OTP required")).not.toBeInTheDocument();
    expect(screen.queryByText("Lake workspace")).not.toBeInTheDocument();
  });
  it("checks existing judge access before listing or enrolling factors", async () => {
    const fake = client(); let approve!: (value: Principal) => void;
    const request = vi.fn(() => new Promise<Principal>((resolve) => { approve = resolve; }));
    render(<MemoryRouter initialEntries={["/verify-2fa"]}><Routes><Route path="/verify-2fa" element={<VerifyOtpPage client={fake as never} request={request as never} />} /><Route path="/lakes" element={<p>Lake workspace</p>} /></Routes></MemoryRouter>);
    await waitFor(() => expect(request).toHaveBeenCalledWith("/api/me", undefined, fake));
    expect(fake.auth.mfa.listFactors).not.toHaveBeenCalled();
    expect(fake.auth.mfa.enroll).not.toHaveBeenCalled();
    await act(async () => { approve(judge); });
    expect(await screen.findByText("Lake workspace")).toBeVisible();
    expect(fake.auth.mfa.enroll).not.toHaveBeenCalled();
  });
  it("does not enroll a factor when the access API is unavailable", async () => {
    const fake = client();
    render(<MemoryRouter><VerifyOtpPage client={fake as never} request={vi.fn().mockRejectedValue(new TypeError("Failed to fetch"))} /></MemoryRouter>);
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not check account access");
    expect(fake.auth.mfa.enroll).not.toHaveBeenCalled();
    expect(fake.auth.mfa.listFactors).not.toHaveBeenCalled();
  });
  it.each([
    { principal: judge, allowed: true },
    { principal: ordinary, allowed: false },
    { principal: { ...judge, memberships: [] }, allowed: false },
    { principal: { ...judge, memberships: [{ ...ordinary.memberships[0], status: "suspended" }] }, allowed: false },
  ])("retains membership checks in route guards ($allowed)", async ({ principal, allowed }) => {
    const request = vi.fn().mockResolvedValue(principal);
    render(<PrincipalProvider client={client() as never} request={request}><MemoryRouter initialEntries={["/guarded"]}><Routes><Route element={<RequireCapability capability="station.read" />}><Route path="/guarded" element={<p>Guarded workspace</p>} /></Route><Route path="/lakes" element={<p>Lake landing</p>} /></Routes></MemoryRouter></PrincipalProvider>);
    expect(await screen.findByText(allowed ? "Guarded workspace" : "Lake landing")).toBeVisible();
  });
  it("retains station and capability scope for an AAL1 judge", () => {
    expect(hasLakeCapability(judge, "station", "station.read")).toBe(true);
    expect(hasLakeCapability(judge, "different", "station.read")).toBe(false);
    expect(hasLakeCapability(judge, "station", "autonomy.manage")).toBe(false);
    expect(hasLakeCapability(ordinary, "station", "station.read")).toBe(false);
  });
  it("labels the judge workspace as a demo", async () => {
    render(<PrincipalProvider client={client() as never} request={vi.fn().mockResolvedValue(judge)}><MemoryRouter><AppHeader active="lakes" client={client() as never} /></MemoryRouter></PrincipalProvider>);
    expect(await screen.findByText("Demo")).toBeVisible();
  });
});
