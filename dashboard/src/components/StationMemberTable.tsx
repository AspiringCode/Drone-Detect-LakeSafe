import { type FormEvent, useEffect, useRef, useState } from "react";
import { AccessibleDialog } from "./AccessibleDialog";
import { Link } from "react-router-dom";
import type { StationMembership } from "../lib/types";
import { apiRequest } from "../lib/apiClient";
import { supabase } from "../lib/supabase";

type Member = { membership_id: string; user_id: string; display_name?: string; status: string; roles: string[] };
const roles = ["viewer", "dispatcher", "safety_supervisor", "station_admin"];
const roleName = (role: string) => role.replace(/_/g, " ").replace(/^./, (letter) => letter.toUpperCase());

export function StationMemberTable({ membership, onChanged }: { membership: StationMembership; onChanged?: () => Promise<void> }) {
  const errorRef = useRef<HTMLDivElement>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => { if (error) errorRef.current?.focus(); }, [error]);
  const [notice, setNotice] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<{member: Member; roles: string[]; status: string} | null>(null);
  useEffect(() => {
    let current = true;
    setLoading(true); setError("");
    void apiRequest<{ members: Member[] }>(`/api/stations/${membership.station_id}/members`, {}, supabase)
      .then((result) => { if (current) setMembers(result.members ?? []); })
      .catch((cause) => { if (current) setError(cause instanceof Error ? cause.message : "Members could not be loaded."); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [membership.station_id, attempt]);

  async function save(event: FormEvent<HTMLFormElement>, member: Member) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const nextRoles = data.getAll("roles").map(String);
    const status = String(data.get("status"));
    if (!nextRoles.length) return setError("Choose at least one station role.");
    if (busy || pending) return;
    setError(""); setPending({member, roles: nextRoles, status});
  }

  async function confirmChange() {
    if (!pending || busy) return;
    const {member, roles: nextRoles, status} = pending;
    setBusy(true); setError(""); setNotice("");
    try {
      await apiRequest(`/api/stations/${membership.station_id}/members/${member.membership_id}`, {
        method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ roles: nextRoles, status }),
      }, supabase);
      setPending(null); setNotice("Member access updated."); setAttempt((value) => value + 1);
      try { await onChanged?.(); } catch { setError("Member access was updated, but your account permissions could not be refreshed. Reload this page before making another change."); }
    } catch (cause) { setPending(null); setError(cause instanceof Error ? cause.message : "Member access could not be changed."); }
    finally { setBusy(false); }
  }

  return <section className="workflow-card station-member-table"><h2>Station members</h2>
    <p className="field-help">Your roles: {membership.roles.map(roleName).join(", ")}. The station must keep an active verified administrator.</p>
    {loading && <p role="status">Loading members…</p>}
    {error && <div role="alert" ref={errorRef} tabIndex={-1}><p className="form-error">{error}</p><button type="button" className="button-secondary" onClick={() => setAttempt((value) => value + 1)}>Retry members</button><p><Link to={`/verify-2fa?returnTo=${encodeURIComponent(`/stations/${membership.station_id}/admin`)}`}>Verify again if recent MFA is required</Link></p></div>}
    {notice && <p className="form-success" role="status">{notice}</p>}
    {!loading && !error && !members.length && <p>No station members were returned.</p>}
    {!loading && members.map((member) => <form key={`${member.membership_id}-${attempt}`} onSubmit={(event) => void save(event, member)} className="member-access-form">
      <h3>{member.display_name || member.user_id}</h3>
      <fieldset disabled={busy}><legend>Station roles</legend>{roles.map((role) => <label className="choice" key={role}><input type="checkbox" name="roles" value={role} defaultChecked={member.roles.includes(role)}/>{roleName(role)}</label>)}</fieldset>
      <label>Membership status<select name="status" defaultValue={member.status} disabled={busy}><option value="active">Active</option><option value="suspended">Suspended</option><option value="revoked">Revoked</option></select></label>
      <button type="submit" className="button-secondary" aria-label={`Save access for ${member.display_name || member.user_id}`} disabled={busy}>{busy ? "Saving…" : "Save access"}</button>
    </form>)}
    {pending && <AccessibleDialog title="Review station access" onClose={() => { if (!busy) setPending(null); }}>
      <p>Change access for <strong>{pending.member.display_name || pending.member.user_id}</strong>?</p>
      <dl className="member-change-summary"><dt>Roles</dt><dd>{pending.roles.map(roleName).join(", ")}</dd><dt>Status</dt><dd>{roleName(pending.status)}</dd></dl>
      {pending.status === "revoked" && <p>This removes their access to this station.</p>}
      <div className="modal-actions"><button disabled={busy} onClick={() => void confirmChange()}>{busy ? "Saving access…" : "Confirm access change"}</button><button className="button-secondary" disabled={busy} onClick={() => setPending(null)}>Cancel</button></div>
    </AccessibleDialog>}
  </section>;
}
