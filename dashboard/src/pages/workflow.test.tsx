import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AuthGate } from "../auth/AuthGate";
import { OnboardingGate } from "../auth/OnboardingGate";
import { LoginPage } from "./LoginPage";
import { SignupPage } from "./SignupPage";
import { VerifyOtpPage } from "./VerifyOtpPage";
import { LakeGridPage } from "./LakeGridPage";
import { LakeLiveView } from "./LakeLiveView";

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
  it("redirects an AAL1 session to TOTP verification", async () => { const { client } = authClient({ currentLevel: "aal1" }); render(gated(client)); expect(await screen.findByText("Verify")).toBeInTheDocument(); });
  it("redirects a verified user without an organization to onboarding", async () => { const { client } = authClient({ orgs: [] }); render(gated(client)); expect(await screen.findByText("Onboarding")).toBeInTheDocument(); });
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
  it("branches a password sign-in according to the session AAL", async () => {
    const auth = { signInWithPassword: vi.fn().mockResolvedValue({ data: { session }, error: null }), mfa: { getAuthenticatorAssuranceLevel: vi.fn().mockResolvedValue({ data: { currentLevel: "aal2" } }) } };
    render(<MemoryRouter><LoginPage client={{ auth } as never} /></MemoryRouter>);
    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: "operator@example.com" } }); fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "secure-password" } }); fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(auth.mfa.getAuthenticatorAssuranceLevel).toHaveBeenCalledWith("token"));
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

  it("renders title-only lake cards without fleet inspection requests", async () => {
    const client = { from: vi.fn(() => ({ select: vi.fn(() => ({ order: vi.fn(() => Promise.resolve({ data: [{ lake_id: "lake-unknown", name: "Quiet Lake" }], error: null })) })) })) };
    render(<MemoryRouter><LakeGridPage client={client as never} /></MemoryRouter>);
    expect(await screen.findByRole("link", { name: "Quiet Lake" })).toBeInTheDocument(); expect(client.from).toHaveBeenCalledTimes(1);
  });

  it("uses the signed-in organization's station coordinates and disables deployment at the cap", async () => {
    const metadataClient = { auth: { getSession: vi.fn().mockResolvedValue({ data: { session } }) }, from: vi.fn(() => ({ select: vi.fn(() => ({ eq: vi.fn(() => ({ maybeSingle: vi.fn().mockResolvedValue({ data: { drone_inventory_cap: 1, organizations: { station_lat: 47.5301, station_lon: -122.0326 } }, error: null }) })) })) })) };
    const fetcher = vi.fn((url: string) => { if (url.includes("riskmap")) return Promise.resolve({ ok: true, status: 200, json: async () => ({ type: "FeatureCollection", features: [] }) }); if (url.includes("alerts")) return Promise.resolve({ ok: true, status: 200, json: async () => [] }); return Promise.resolve({ ok: true, status: 200, json: async () => ({}) }); });
    render(<MemoryRouter initialEntries={["/lakes/lake-sammamish"]}><Routes><Route path="/lakes/:lakeId" element={<LakeLiveView client={metadataClient as never} accessToken="token" fetcher={fetcher as never} connect={(_url, onState) => { onState({ drones: [{ drone_id: "d1", pos: { lat: 1, lon: 1 }, battery: 1, status: "idle", assigned_zone: null, source: "simulated" }], conflicts: [], t: 0 }); return () => {}; }} />} /></Routes></MemoryRouter>);
    expect(await screen.findByTestId("lake-map")).toHaveTextContent("47.5301,-122.0326"); const deploy = screen.getByRole("button", { name: /inventory cap reached/i }); expect(deploy).toBeDisabled(); expect(fetcher).not.toHaveBeenCalledWith(expect.stringContaining("/drones/deploy"), expect.anything());
  });

  it("reports a backend inventory-cap conflict that races the client-side check", async () => {
    const metadataClient = { auth: { getSession: vi.fn().mockResolvedValue({ data: { session } }) }, from: vi.fn(() => ({ select: vi.fn(() => ({ eq: vi.fn(() => ({ maybeSingle: vi.fn().mockResolvedValue({ data: { drone_inventory_cap: 5, organizations: { station_lat: 47.5301, station_lon: -122.0326 } }, error: null }) })) })) })) };
    const fetcher = vi.fn((url: string) => { if (url.includes("riskmap")) return Promise.resolve({ ok: true, status: 200, json: async () => ({ type: "FeatureCollection", features: [] }) }); if (url.includes("alerts")) return Promise.resolve({ ok: true, status: 200, json: async () => [] }); if (url.includes("deploy")) return Promise.resolve({ ok: false, status: 409, json: async () => ({ detail: "Drone inventory cap reached" }) }); return Promise.resolve({ ok: true, status: 200, json: async () => ({}) }); });
    render(<MemoryRouter initialEntries={["/lakes/lake-sammamish"]}><Routes><Route path="/lakes/:lakeId" element={<LakeLiveView client={metadataClient as never} accessToken="token" fetcher={fetcher as never} connect={() => () => {}} />} /></Routes></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /deploy drone/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/inventory cap reached/i);
  });
});
