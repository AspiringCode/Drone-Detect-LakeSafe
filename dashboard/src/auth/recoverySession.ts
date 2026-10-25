import { supabase } from "../lib/supabase";
// Register eagerly, before lazy route loading can miss the SDK's recovery event.
type RecoverySession = { access_token: string; expires_at?: number; user?: { id: string } };
let recoverySession: RecoverySession | null = null;
supabase.auth.onAuthStateChange((event, session) => {
  if (event === "PASSWORD_RECOVERY") recoverySession = session;
  else if (event === "SIGNED_OUT" || event === "USER_UPDATED" || event === "SIGNED_IN") recoverySession = null;
});
export function getRecoverySession() { return recoverySession; }
export function advanceRecoverySession(previousToken: string, verified: RecoverySession): boolean {
  if (!recoverySession || recoverySession.access_token !== previousToken || !verified.user?.id || verified.user.id !== recoverySession.user?.id) return false;
  recoverySession = verified;
  return true;
}
