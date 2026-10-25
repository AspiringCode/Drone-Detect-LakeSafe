import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AuthGate } from "../auth/AuthGate";
import { SignupPage } from "./SignupPage";
import { LoginPage } from "./LoginPage";
import { VerifyOtpPage } from "./VerifyOtpPage";
import { ForgotPasswordPage, ResetPasswordPage } from "./PasswordRecoveryPages";
function Location() { const location = useLocation(); return <p>{location.pathname + location.search}</p>; }
const destination = "/invitations/accept?token=example";
const query = `?returnTo=${encodeURIComponent(destination)}`;
const subscription = () => ({ data: { subscription: { unsubscribe() {} } } });
describe("authentication recovery journeys", () => {
  it("verifies the existing authenticator before changing an enrolled recovery account password", async () => {
    let current = { access_token: "recovery", expires_at: Math.floor(Date.now() / 1000) + 60, user: { id: "user-1" } };
    const updateUser = vi.fn().mockResolvedValue({ error: null });
    const verify = vi.fn().mockImplementation(async () => { current = { ...current, access_token: "recovery-aal2" }; return { data: current, error: null }; });
    const client = { auth: {
      getSession: async () => ({ data: { session: current } }), updateUser, signOut: vi.fn().mockResolvedValue({ error: null }),
      onAuthStateChange: (callback: (event: string, session: unknown) => void) => { queueMicrotask(() => callback("PASSWORD_RECOVERY", current)); return subscription(); },
      mfa: { listFactors: async () => ({ data: { totp: [{ id: "existing-factor", status: "verified" }] } }),
        challenge: vi.fn().mockResolvedValue({ data: { id: "challenge-1" }, error: null }), verify,
        getAuthenticatorAssuranceLevel: async () => ({ data: { currentLevel: "aal2" }, error: null }) },
    } };
    render(<MemoryRouter><ResetPasswordPage client={client}/></MemoryRouter>);
    fireEvent.change(await screen.findByLabelText("New password"), { target: { value: "new-password" } });
    fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: "new-password" } });
    fireEvent.change(await screen.findByLabelText("Authentication code"), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Update password" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Password updated");
    expect(verify).toHaveBeenCalledWith({ factorId: "existing-factor", challengeId: "challenge-1", code: "123456" });
    expect(updateUser).toHaveBeenCalledOnce();
  });
  it("never updates the password if the recovery authenticator rejects the code", async () => {
    const session = { access_token: "recovery", expires_at: Math.floor(Date.now() / 1000) + 60, user: { id: "user-1" } };
    const updateUser = vi.fn();
    const client = { auth: { getSession: async () => ({ data: { session } }), updateUser,
      onAuthStateChange: (callback: (event: string, session: unknown) => void) => { queueMicrotask(() => callback("PASSWORD_RECOVERY", session)); return subscription(); },
      mfa: { listFactors: async () => ({ data: { totp: [{ id: "factor", status: "verified" }] } }), challenge: async () => ({ data: { id: "c" } }), verify: async () => ({ error: { message: "Invalid code" } }) },
    } };
    render(<MemoryRouter><ResetPasswordPage client={client}/></MemoryRouter>);
    fireEvent.change(await screen.findByLabelText("New password"), { target: { value: "new-password" } });
    fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: "new-password" } });
    fireEvent.change(await screen.findByLabelText("Authentication code"), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Update password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("authenticator");
    expect(updateUser).not.toHaveBeenCalled();
  });
  it("preserves the signed-out invitation destination", async () => {
    const client = { auth: { getSession: async () => ({ data: { session: null } }), onAuthStateChange: subscription } };
    render(<MemoryRouter initialEntries={[destination]}><Routes><Route element={<AuthGate client={client} />}><Route path="/invitations/accept" element={<p>Invitation</p>} /></Route><Route path="/login" element={<Location />} /></Routes></MemoryRouter>);
    expect(await screen.findByText(`/login${query}`)).toBeVisible();
  });
  it("offers a retry when session lookup fails", async () => {
    const getSession = vi.fn().mockRejectedValueOnce(new Error("network")).mockResolvedValue({ data: { session: null } });
    render(<MemoryRouter initialEntries={[destination]}><Routes><Route element={<AuthGate client={{ auth: { getSession, onAuthStateChange: subscription } }} />}><Route path="/invitations/accept" element={<p>Invitation</p>} /></Route><Route path="/login" element={<Location />} /></Routes></MemoryRouter>);
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not check your session");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText(`/login${query}`)).toBeVisible();
  });
  it("preserves an invitation through password and MFA verification", async () => {
    const client = { auth: { signInWithPassword: async () => ({ data: { session: { access_token: "token" } } }), mfa: { getAuthenticatorAssuranceLevel: async () => ({ data: { currentLevel: "aal1" } }), listFactors: async () => ({ data: { totp: [{ id: "factor", status: "verified" }] } }), challenge: async () => ({ data: { id: "challenge" } }), verify: async () => ({ error: null }) } } };
    const request = vi.fn().mockResolvedValue({ judge_demo_access: false });
    render(<MemoryRouter initialEntries={[`/login${query}`]}><Routes><Route path="/login" element={<LoginPage client={client} request={request} />} /><Route path="/verify-2fa" element={<VerifyOtpPage client={client} request={request} />} /><Route path="/invitations/accept" element={<Location />} /></Routes></MemoryRouter>);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "operator@example.test" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    fireEvent.change(await screen.findByLabelText("Authentication code"), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify code" }));
    expect(await screen.findByText(destination)).toBeVisible();
  });
  it("locks password sign-in while the request is pending", () => {
    const signInWithPassword = vi.fn(() => new Promise(() => {}));
    render(<MemoryRouter><LoginPage client={{ auth: { signInWithPassword } }} /></MemoryRouter>);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "operator@example.test" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password" } });
    fireEvent.submit(screen.getByRole("button", { name: "Sign in" }).closest("form")!);
    expect(screen.getByRole("button", { name: "Signing in…" })).toBeDisabled();
    fireEvent.submit(screen.getByRole("button", { name: "Signing in…" }).closest("form")!);
    expect(signInWithPassword).toHaveBeenCalledOnce();
  });
  it("locks account creation while enrollment is pending", () => {
    const signUp = vi.fn(() => new Promise(() => {}));
    render(<MemoryRouter><SignupPage client={{ auth: { signUp } }} /></MemoryRouter>);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "operator@example.test" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password" } });
    const form = screen.getByRole("button", { name: "Create account" }).closest("form")!;
    fireEvent.submit(form); fireEvent.submit(form);
    expect(signUp).toHaveBeenCalledOnce();
    expect(screen.getByRole("button", { name: "Creating account…" })).toBeDisabled();
  });
  it("locks MFA verification while the challenge is pending", async () => {
    const challenge = vi.fn(() => new Promise(() => {}));
    const client = { auth: { mfa: { listFactors: async () => ({ data: { totp: [{ id: "factor", status: "verified" }] } }), challenge } } };
    render(<MemoryRouter><VerifyOtpPage client={client} request={vi.fn().mockResolvedValue({ judge_demo_access: false })} /></MemoryRouter>);
    fireEvent.change(await screen.findByLabelText("Authentication code"), { target: { value: "123456" } });
    const form = screen.getByRole("button", { name: "Verify code" }).closest("form")!;
    fireEvent.submit(form); fireEvent.submit(form);
    expect(challenge).toHaveBeenCalledOnce();
    expect(screen.getByRole("button", { name: "Verifying…" })).toBeDisabled();
  });
  it("requests a same-origin recovery link without revealing account existence", async () => {
    const resetPasswordForEmail = vi.fn().mockResolvedValue({ error: null });
    render(<MemoryRouter><ForgotPasswordPage client={{ auth: { resetPasswordForEmail } }} /></MemoryRouter>);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "operator@example.test" } });
    fireEvent.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(await screen.findByRole("status")).toHaveTextContent("If an account exists");
    expect(resetPasswordForEmail).toHaveBeenCalledWith("operator@example.test", { redirectTo: `${window.location.origin}/reset-password` });
  });
  it("shows a usable retry after a recovery request fails", async () => {
    render(<MemoryRouter><ForgotPasswordPage client={{ auth: { resetPasswordForEmail: async () => { throw new Error("network"); } } }} /></MemoryRouter>);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "operator@example.test" } });
    fireEvent.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not send");
    expect(screen.getByRole("button", { name: "Send reset link" })).toBeEnabled();
  });
  it("rejects an ordinary session without a recovery event", async () => {
    const updateUser = vi.fn();
    render(<MemoryRouter><ResetPasswordPage client={{ auth: { getSession: async () => ({ data: { session: { access_token: "ordinary" } } }), onAuthStateChange: subscription, updateUser } }} /></MemoryRouter>);
    expect(await screen.findByRole("alert")).toHaveTextContent("expired or invalid");
    expect(screen.queryByLabelText("New password")).not.toBeInTheDocument();
    expect(updateUser).not.toHaveBeenCalled();
  });
  it("rejects an expired recovery session", async () => {
    const updateUser = vi.fn();
    const expired = { access_token: "expired", expires_at: 1 };
    render(<MemoryRouter><ResetPasswordPage client={{ auth: { getSession: async () => ({ data: { session: expired } }), onAuthStateChange: (callback: (event: string, session: unknown) => void) => { queueMicrotask(() => callback("PASSWORD_RECOVERY", expired)); return subscription(); }, updateUser } }} /></MemoryRouter>);
    expect(await screen.findByRole("alert")).toHaveTextContent("expired or invalid");
    expect(updateUser).not.toHaveBeenCalled();
    expect(screen.getByRole("link", { name: "Request a new reset link" })).toBeVisible();
  });
  it("shows update failures and retains an explicit retry", async () => {
    const session = { access_token: "recovery", expires_at: Math.floor(Date.now() / 1000) + 60 };
    const updateUser = vi.fn().mockResolvedValue({ error: { message: "expired" } });
    render(<MemoryRouter><ResetPasswordPage client={{ auth: { getSession: async () => ({ data: { session } }), onAuthStateChange: (callback: (event: string, session: unknown) => void) => { queueMicrotask(() => callback("PASSWORD_RECOVERY", session)); return subscription(); }, updateUser } }} /></MemoryRouter>);
    fireEvent.change(await screen.findByLabelText("New password"), { target: { value: "new-password" } });
    fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: "new-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Update password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not update");
    expect(screen.getByRole("button", { name: "Update password" })).toBeEnabled();
  });
  it("only updates after a recovery event and explicit matching-password submission", async () => {
    let listener: (event: string, session: unknown) => void = () => {};
    const updateUser = vi.fn().mockResolvedValue({ error: null });
    const client = { auth: { getSession: async () => ({ data: { session: { access_token: "recovery", expires_at: Math.floor(Date.now() / 1000) + 60 } } }), onAuthStateChange: (callback: typeof listener) => { listener = callback; queueMicrotask(() => listener("PASSWORD_RECOVERY", { access_token: "recovery", expires_at: Math.floor(Date.now() / 1000) + 60 })); return subscription(); }, updateUser, signOut: vi.fn().mockResolvedValue({ error: null }) } };
    render(<MemoryRouter><ResetPasswordPage client={client} /></MemoryRouter>);
    fireEvent.change(await screen.findByLabelText("New password"), { target: { value: "new-password" } });
    fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: "new-password" } });
    expect(updateUser).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Update password" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Password updated");
    expect(updateUser).toHaveBeenCalledWith({ password: "new-password" });
    expect(client.auth.signOut).toHaveBeenCalledWith({ scope: "local" });
  });
});
