import { describe, expect, it } from "vitest";
import { safeReturnTo, authDestination } from "./returnTo";
describe("safe return destinations", () => {
  it("retains an invitation query and fragment", () => expect(safeReturnTo("/invitations/accept?token=example#accept")).toBe("/invitations/accept?token=example#accept"));
  it.each(["https://evil.test", "//evil.test", "/\\evil.test", "/login", "/%6cogin", "/%2flogin", "https://operator:password@evil.test", "/reset-password", "/%2f%2fevil.test", "/lakes\n"])('rejects unsafe or looping destination %s', value => expect(safeReturnTo(value)).toBe("/lakes"));
  it("carries the destination to MFA", () => expect(authDestination("/verify-2fa", "/invitations/accept?token=example")).toBe("/verify-2fa?returnTo=%2Finvitations%2Faccept%3Ftoken%3Dexample"));
});
