import { type FormEvent, useEffect, useState } from "react";
import { AppHeader } from "../components/AppHeader";
import { supabase, type SupabaseLike } from "../lib/supabase";
import { Link } from "react-router-dom";
import { useOptionalPrincipal } from "../auth/PrincipalProvider";

type ProfileState = {
  id: string;
  email: string;
  displayName: string;
};

export function ProfileSettingsPage({ client = supabase }: { client?: SupabaseLike }) {
  const principal = useOptionalPrincipal()?.principal;
  const [profile, setProfile] = useState<ProfileState | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [loadingError, setLoadingError] = useState("");
  const [saveError, setSaveError] = useState("");
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let current = true;
    void client.auth.getUser().then(({ data, error }: { data: { user: any }; error: any }) => {
      if (!current) return;
      if (error || !data.user) return setLoadingError("Could not load your profile.");
      const nextProfile = {
        id: data.user.id,
        email: data.user.email ?? "",
        displayName: data.user.user_metadata?.display_name ?? "",
      };
      setProfile(nextProfile);
      setDisplayName(nextProfile.displayName);
    });
    return () => { current = false; };
  }, [client]);

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setSaved(false);
    setSaveError("");
    const { error } = await client.auth.updateUser({ data: { display_name: displayName.trim() } });
    setSaving(false);
    if (error) return setSaveError("Could not save your profile. Please try again.");
    setProfile((current) => current ? { ...current, displayName: displayName.trim() } : current);
    setDisplayName(displayName.trim());
    setSaved(true);
  }

  return (
    <main className="app-page profile-page">
      <AppHeader active="profile" contextLabel="Account settings" client={client} />
      <section className="profile-shell">
        <header className="page-heading">
          <h1>Profile settings</h1>
          <p>Manage the identity shown across your LakeSafe workspace.</p>
        </header>

        <section className="profile-card verification-card" aria-labelledby="verification-title">
          <p className="panel-eyebrow">Affiliation</p>
          <h2 id="verification-title">Verification: {(principal?.verification_status ?? "not started").replace(/_/g, " ")}</h2>
          <p className="field-help">Verification is separate from station membership and never grants access on its own.</p>
          <Link className="button-link" to="/verify-affiliation">{principal?.verification_status === "verified" ? "View verification" : "Verify affiliation"}</Link>
        </section>

        <section className="profile-card" aria-labelledby="profile-details-title">
          <div className="profile-card__heading">
            <div>
              <p className="panel-eyebrow">Personal details</p>
              <h2 id="profile-details-title">Your profile</h2>
            </div>
            <span className="profile-avatar" aria-hidden="true">{(profile?.displayName || profile?.email || "O").charAt(0).toUpperCase()}</span>
          </div>

          {loadingError && <p className="form-error" role="alert">{loadingError}</p>}
          {!profile && !loadingError && <p className="panel-empty" aria-live="polite">Loading your profile…</p>}
          {profile && (
            <form className="profile-form" onSubmit={saveProfile}>
              <label>
                Display name
                <input value={displayName} onChange={(event) => { setDisplayName(event.target.value); setSaved(false); }} maxLength={80} placeholder="Lake operator" />
              </label>
              <label>
                Email address
                <input value={profile.email} readOnly aria-describedby="email-help" />
                <span id="email-help" className="field-help">Email changes are managed through your Supabase account.</span>
              </label>
              <label>
                User ID
                <input className="profile-id" value={profile.id} readOnly />
              </label>
              {saveError && <p className="form-error" role="alert">{saveError}</p>}
              {saved && <p className="form-success" role="status"><span className="status-dot" aria-hidden="true" />Profile saved.</p>}
              <div className="profile-actions">
                <button type="submit" disabled={saving || displayName.trim() === profile.displayName}>
                  {saving ? "Saving…" : "Save changes"}
                </button>
              </div>
            </form>
          )}
        </section>
      </section>
    </main>
  );
}
