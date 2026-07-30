import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AuthGate } from "../auth/AuthGate";
import { OnboardingGate } from "../auth/OnboardingGate";
import { PrincipalProvider } from "../auth/PrincipalProvider";
import { ActiveStationProvider } from "../hooks/useActiveStation";
import { LoginPage } from "./LoginPage";
import { SignupPage } from "./SignupPage";
import { VerifyOtpPage } from "./VerifyOtpPage";
import { LakeGridPage } from "./LakeGridPage";
import { hasLakeCapability, LakeLiveView } from "./LakeLiveView";
import type { Principal } from "../lib/types";
import { OnboardingPage } from "./OnboardingPage";

vi.mock("../components/LakeMap", () => ({
  LakeMap: ({ stationLocation }: { stationLocation: { lat: number; lon: number } }) => <div data-testid="lake-map">{stationLocation.lat},{stationLocation.lon}</div>,
}));

const session = { access_token: "token" };
function authClient({ currentLevel = "aal2", hasSession = true, orgs = [{ org_id: "org-1" }] }: { currentLevel?: string; hasSession?: boolean; orgs?: Array<{ org_id: string }> } = {}) {
  const callback = vi.fn();
  const unsubscribe = vi.fn();
  const client = {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: hasSession ? session : null } }),
      onAuthStateChange: vi.fn((listener) => { callback.mockImplementation(listener); return { data: { subscription: { unsubscribe } } }; }),
      mfa: { getAuthenticatorAssuranceLevel: vi.fn().mockResolvedValue({ data: { currentLevel } }) },
    },
    from: vi.fn(() => ({ select: vi.fn(() => ({ limit: vi.fn().mockResolvedValue({ data: orgs, error: null }) })) })),
  };
  return { client, callback, unsubscribe };
}

function gated(client: unknown) {
  return <MemoryRouter initialEntries={["/lakes"]}><Routes><Route element={<AuthGate client={client as never} />}><Route path="/lakes" element={<p>Protected lakes</p>} /></Route><Route path="/login" element={<p>Login</p>} /><Route path="/verify-2fa" element={<p>Verify</p>} /><Route path="/onboarding" element={<p>Onboarding</p>} /></Routes></MemoryRouter>;
}

function onboardingGated(client: unknown) {
  return <MemoryRouter initialEntries={["/onboarding"]}><Routes><Route element={<OnboardingGate client={client as never} />}><Route path="/onboarding" element={<p>Onboarding</p>} /></Route><Route path="/login" element={<p>Login</p>} /><Route path="/verify-2fa" element={<p>Verify</p>} /></Routes></MemoryRouter>;
}

describe("AuthGate", () => {
  it("redirects a visitor without a session to login", async () => { const { client } = authClient({ hasSession: false }); render(gated(client)); expect(await screen.findByText("Login")).toBeInTheDocument(); });
  it("permits an AAL1 civilian session into the public workspace", async () => { const { client } = authClient({ currentLevel: "aal1" }); render(gated(client)); expect(await screen.findByText("Protected lakes")).toBeInTheDocument(); });
  it("permits a civilian without an organization into the public workspace", async () => { const { client } = authClient({ orgs: [] }); render(gated(client)); expect(await screen.findByText("Protected lakes")).toBeInTheDocument(); });
  it("permits an AAL2 user with an organization and listens for auth changes", async () => { const { client, unsubscribe } = authClient(); const { unmount } = render(gated(client)); expect(await screen.findByText("Protected lakes")).toBeInTheDocument(); expect(client.auth.onAuthStateChange).toHaveBeenCalledOnce(); unmount(); expect(unsubscribe).toHaveBeenCalledOnce(); });
});

describe("OnboardingGate", () => {
  it("allows an AAL2 session without an organization and re-evaluates on auth changes", async () => {
    const { client, callback } = authClient({ orgs: [] });
    render(onboardingGated(client));
    expect(await screen.findByText("Onboarding")).toBeInTheDocument();

    client.auth.getSession.mockResolvedValue({ data: { session: null } });
    callback("SIGNED_OUT", null);

    expect(await screen.findByText("Login")).toBeInTheDocument();
    await waitFor(() => expect(client.auth.getSession).toHaveBeenCalledTimes(2));
  });
});

describe("operator workflow", () => {
  it("uses the authenticated operational connector only for the lake's matching station", async () => {
    const principal: Principal = { user_id: "officer", email: "officer@example.gov", aal: "aal2", account_class: "officer", verification_status: "verified", reviewer: false, memberships: [{ station_id: "station-a", station_name: "A", status: "active", roles: ["station_admin"], capabilities: ["station.read", "inventory.manage"] }] };
    const auth = { getSession: vi.fn().mockResolvedValue({ data: { session } }), onAuthStateChange: vi.fn(() => ({ data: { subscription: { unsubscribe: vi.fn() } } })) };
    const client = { auth, from: vi.fn(() => ({ select: vi.fn(() => ({ eq: vi.fn(() => ({ maybeSingle: vi.fn().mockResolvedValue({ data: { station_id: "station-a", drone_inventory_cap: 5, organizations: { station_lat: 47.5, station_lon: -122.1 } }, error: null }) })) })) })) };
    const operational = vi.fn(() => () => {});
    const fetcher = vi.fn((url: string) => Promise.resolve({ ok: true, status: 200, json: async () => url.includes("alerts") ? [] : { type: "FeatureCollection", features: [] } }));
    render(<PrincipalProvider client={client as never} request={(async () => principal) as never}><ActiveStationProvider><MemoryRouter initialEntries={["/lakes/lake-sammamish"]}><Routes><Route path="/lakes/:lakeId" element={<LakeLiveView client={client as never} fetcher={fetcher as never} connectOperational={operational as never} />} /></Routes></MemoryRouter></ActiveStationProvider></PrincipalProvider>);
    expect(await screen.findByRole("button", { name: /deploy drone/i })).toBeInTheDocument();
    await waitFor(() => expect(operational).toHaveBeenCalledWith(expect.stringContaining("/ws/operations/lakes/lake-sammamish"), "token", expect.any(Function)));
  });
  it("does not borrow a capability from a different station's membership", () => {
    const principal: Principal = { user_id: "officer", email: "officer@example.gov", aal: "aal2", account_class: "officer", verification_status: "verified", reviewer: false, memberships: [
      { station_id: "station-b", station_name: "B", status: "active", roles: ["station_admin"], capabilities: ["station.read", "inventory.manage", "alert.manage"] },
    ] };
    expect(hasLakeCapability(principal, "station-a", "station.read")).toBe(false);
    expect(hasLakeCapability(principal, "station-a", "inventory.manage")).toBe(false);
    expect(hasLakeCapability(principal, "station-b", "inventory.manage")).toBe(true);
  });
  it("branches a password sign-in according to the session AAL", async () => {
    const auth = { signInWithPassword: vi.fn().mockResolvedValue({ data: { session }, error: null }), mfa: { getAuthenticatorAssuranceLevel: vi.fn().mockResolvedValue({ data: { currentLevel: "aal2" } }) } };
    render(<MemoryRouter><LoginPage client={{ auth } as never} /></MemoryRouter>);
    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: "operator@example.com" } }); fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "secure-password" } }); fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(auth.mfa.getAuthenticatorAssuranceLevel).toHaveBeenCalledWith("token"));
  });

  it("restores onboarding search controls after a network failure", async () => {
    const fetcher = vi.fn().mockRejectedValue(new TypeError("network unavailable"));
    render(<MemoryRouter><OnboardingPage fetcher={fetcher} /></MemoryRouter>);
    fireEvent.change(screen.getByLabelText(/station name/i), { target: { value: "LakeSafe" } });
    fireEvent.change(screen.getByLabelText(/station address/i), { target: { value: "Sammamish, WA" } });
    fireEvent.click(screen.getByRole("button", { name: /find nearby lakes/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not find lakes/i);
    expect(screen.getByRole("button", { name: /find nearby lakes/i })).toBeEnabled();
  });

  it("enrolls a genuine TOTP factor, presents it, and verifies the enrollment", async () => {
    const auth = { signUp: vi.fn().mockResolvedValue({ data: { session }, error: null }), mfa: { enroll: vi.fn().mockResolvedValue({ data: { id: "factor-1", totp: { qr_code: "data:image/svg+xml,test", secret: "SECRET" } }, error: null }), challenge: vi.fn().mockResolvedValue({ data: { id: "challenge-1" }, error: null }), verify: vi.fn().mockResolvedValue({ error: null }) } };
    render(<MemoryRouter><SignupPage client={{ auth } as never} /></MemoryRouter>);
    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: "operator@example.com" } }); fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "secure-password" } }); fireEvent.click(screen.getByRole("button", { name: /create account/i }));
    expect(await screen.findByAltText(/totp qr code/i)).toBeInTheDocument(); expect(screen.getByLabelText(/setup key/i)).toHaveValue("SECRET"); expect(auth.mfa.enroll).toHaveBeenCalledWith({ factorType: "totp", friendlyName: "LakeSafe operator" });
    fireEvent.change(screen.getByLabelText(/authentication code/i), { target: { value: "123456" } }); fireEvent.click(screen.getByRole("button", { name: /verify and continue/i }));
    await waitFor(() => expect(auth.mfa.verify).toHaveBeenCalledWith({ factorId: "factor-1", challengeId: "challenge-1", code: "123456" }));
  });

  it("enrolls TOTP for a signed-in operator with no verified factor and verifies it", async () => {
    const auth = { mfa: { listFactors: vi.fn().mockResolvedValue({ data: { totp: [] }, error: null }), enroll: vi.fn().mockResolvedValue({ data: { id: "factor-2", totp: { qr_code: "data:image/svg+xml,test", secret: "EXISTING-SECRET" } }, error: null }), challenge: vi.fn().mockResolvedValue({ data: { id: "challenge-2" }, error: null }), verify: vi.fn().mockResolvedValue({ error: null }) } };
    render(<MemoryRouter><VerifyOtpPage client={{ auth } as never} /></MemoryRouter>);

    expect(await screen.findByAltText(/totp qr code/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/setup key/i)).toHaveValue("EXISTING-SECRET");
    expect(auth.mfa.enroll).toHaveBeenCalledWith({ factorType: "totp", friendlyName: "LakeSafe operator" });

    fireEvent.change(screen.getByLabelText(/authentication code/i), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: /verify and continue/i }));
    await waitFor(() => expect(auth.mfa.verify).toHaveBeenCalledWith({ factorId: "factor-2", challengeId: "challenge-2", code: "123456" }));
  });

  it("renders lake cards with geographic previews without fleet inspection requests", async () => {
    const client = { from: vi.fn(() => ({ select: vi.fn(() => ({ order: vi.fn(() => Promise.resolve({ data: [{ lake_id: "lake-unknown", name: "Quiet Lake", org_id: "org-1", centroid_lat: 47.58, centroid_lon: -122.09 }], error: null })) })) })) };
    render(<MemoryRouter><LakeGridPage client={client as never} /></MemoryRouter>);
    expect(await screen.findByRole("link", { name: /quiet lake/i })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /quiet lake map preview/i })).toBeInTheDocument();
    expect(client.from).toHaveBeenCalledWith("lakes");
  });

  it("filters managed lakes when the operator chooses a station", async () => {
    const lakes = [
      { lake_id: "lake-one", name: "First Lake", org_id: "org-1", centroid_lat: 1, centroid_lon: 1 },
      { lake_id: "lake-two", name: "Second Lake", org_id: "org-2", centroid_lat: 2, centroid_lon: 2 },
    ];
    const client = {
      auth: { getUser: vi.fn().mockResolvedValue({ data: { user: null } }) },
      from: vi.fn((table: string) => table === "organizations"
        ? { select: vi.fn().mockResolvedValue({ data: [{ org_id: "org-1", name: "Station One" }, { org_id: "org-2", name: "Station Two" }] }) }
        : { select: vi.fn(() => ({ order: vi.fn().mockResolvedValue({ data: lakes, error: null }) })) }),
    };

    render(<MemoryRouter initialEntries={["/lakes?station=org-2"]}><LakeGridPage client={client as never} /></MemoryRouter>);

    expect(await screen.findByRole("link", { name: /second lake/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /first lake/i })).toBeInTheDocument();
  });

  it("uses the signed-in organization's station coordinates and disables deployment at the cap", async () => {
    const metadataClient = { auth: { getSession: vi.fn().mockResolvedValue({ data: { session } }) }, from: vi.fn(() => ({ select: vi.fn(() => ({ eq: vi.fn(() => ({ maybeSingle: vi.fn().mockResolvedValue({ data: { drone_inventory_cap: 1, organizations: { station_lat: 47.5301, station_lon: -122.0326 } }, error: null }) })) })) })) };
    const fetcher = vi.fn((url: string) => { if (url.includes("riskmap")) return Promise.resolve({ ok: true, status: 200, json: async () => ({ type: "FeatureCollection", features: [] }) }); if (url.includes("alerts")) return Promise.resolve({ ok: true, status: 200, json: async () => [] }); return Promise.resolve({ ok: true, status: 200, json: async () => ({}) }); });
    render(<MemoryRouter initialEntries={["/lakes/lake-sammamish"]}><Routes><Route path="/lakes/:lakeId" element={<LakeLiveView client={metadataClient as never} accessToken="token" fetcher={fetcher as never} connect={(_url, onState) => { onState({ drones: [{ drone_id: "d1", pos: { lat: 1, lon: 1 }, battery: 1, status: "idle", assigned_zone: null, source: "simulated" }], conflicts: [], t: 0 }); return () => {}; }} />} /></Routes></MemoryRouter>);
    expect(await screen.findByTestId("lake-map")).toHaveTextContent("47.5301,-122.0326");
    const fleetCard = screen.getByRole("heading", { name: /drone status/i }).closest("section");
    expect(fleetCard).not.toBeNull();
    expect(within(fleetCard!).getByRole("alert")).toHaveTextContent(/fleet capacity reached/i);
    const breadcrumb = screen.getByRole("navigation", { name: /breadcrumb/i });
    expect(breadcrumb).toHaveTextContent("Lakes > Operations");
    expect(within(breadcrumb).getByRole("link", { name: "Lakes" })).toHaveAttribute("href", "/lakes");
    expect(screen.queryByText("Live operations")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /inventory cap reached/i })).not.toBeInTheDocument();
    expect(fetcher).not.toHaveBeenCalledWith(expect.stringContaining("/drones/deploy"), expect.anything());
  });

  it("reports a backend inventory-cap conflict that races the client-side check", async () => {
    const metadataClient = { auth: { getSession: vi.fn().mockResolvedValue({ data: { session } }) }, from: vi.fn(() => ({ select: vi.fn(() => ({ eq: vi.fn(() => ({ maybeSingle: vi.fn().mockResolvedValue({ data: { drone_inventory_cap: 5, organizations: { station_lat: 47.5301, station_lon: -122.0326 } }, error: null }) })) })) })) };
    const fetcher = vi.fn((url: string) => { if (url.includes("riskmap")) return Promise.resolve({ ok: true, status: 200, json: async () => ({ type: "FeatureCollection", features: [] }) }); if (url.includes("alerts")) return Promise.resolve({ ok: true, status: 200, json: async () => [] }); if (url.includes("deploy")) return Promise.resolve({ ok: false, status: 409, json: async () => ({ detail: "Drone inventory cap reached" }) }); return Promise.resolve({ ok: true, status: 200, json: async () => ({}) }); });
    render(<MemoryRouter initialEntries={["/lakes/lake-sammamish"]}><Routes><Route path="/lakes/:lakeId" element={<LakeLiveView client={metadataClient as never} accessToken="token" fetcher={fetcher as never} connect={() => () => {}} />} /></Routes></MemoryRouter>);
    await screen.findByRole("heading", { name: /drone status/i });
    expect(screen.queryByRole("button", { name: /deploy drone/i })).not.toBeInTheDocument();
    expect(fetcher).not.toHaveBeenCalledWith(expect.stringContaining("/drones/deploy"), expect.anything());
  });
});
