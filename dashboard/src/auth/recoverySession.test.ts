import { beforeEach, describe, expect, it, vi } from "vitest";
const capture = vi.hoisted(() => ({ listener: (_event: string, _session: unknown) => {} }));
vi.mock("../lib/supabase", () => ({ supabase: { auth: { onAuthStateChange: (listener: typeof capture.listener) => { capture.listener = listener; } } } }));
import { advanceRecoverySession, getRecoverySession } from "./recoverySession";
describe("early recovery session capture", () => {
  const emit = (event: string, session: unknown) => capture.listener(event, session);
  beforeEach(() => emit("SIGNED_OUT", null));
  it("captures recovery before a lazy screen loads", () => {
    const session = { access_token: "recovery", expires_at: 123 };
    emit("PASSWORD_RECOVERY", session);
    expect(getRecoverySession()).toBe(session);
  });
  it("does not treat an ordinary sign-in as recovery", () => {
    emit("SIGNED_IN", { access_token: "ordinary" });
    expect(getRecoverySession()).toBeNull();
  });
  it("only advances an existing recovery chain for the same user after verification", () => {
    emit("PASSWORD_RECOVERY", { access_token: "recovery", user: { id: "u-1" } });
    expect(advanceRecoverySession("wrong-token", { access_token: "aal2", user: { id: "u-1" } })).toBe(false);
    expect(advanceRecoverySession("recovery", { access_token: "aal2", user: { id: "u-2" } })).toBe(false);
    expect(advanceRecoverySession("recovery", { access_token: "aal2", user: { id: "u-1" } })).toBe(true);
    expect(getRecoverySession()?.access_token).toBe("aal2");
    emit("SIGNED_IN", { access_token: "ordinary", user: { id: "u-1" } });
    expect(advanceRecoverySession("aal2", { access_token: "other", user: { id: "u-1" } })).toBe(false);
  });
  it.each(["SIGNED_OUT", "USER_UPDATED", "SIGNED_IN"])("clears recovery on %s", event => {
    emit("PASSWORD_RECOVERY", { access_token: "recovery" });
    emit(event, null);
    expect(getRecoverySession()).toBeNull();
  });
});
