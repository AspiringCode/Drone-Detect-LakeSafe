import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { supabase, type SupabaseLike } from "../lib/supabase";

type AppHeaderProps = {
  active: "lakes" | "operations" | "profile";
  contextLabel?: string;
  client?: SupabaseLike;
};

export function AppHeader({ active, contextLabel, client = supabase }: AppHeaderProps) {
  const navigate = useNavigate();
  const [signingOut, setSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState("");

  async function signOut() {
    setSigningOut(true);
    setSignOutError("");
    const { error } = await client.auth.signOut();
    setSigningOut(false);
    if (error) return setSignOutError("Could not sign out. Please try again.");
    navigate("/login", { replace: true });
  }

  return (
    <header className="app-header">
      <Link className="app-brand" to="/lakes" aria-label="LakeSafe managed lakes">
        <span className="app-brand__name">LakeSafe</span>
        <span className="app-brand__mark" aria-hidden="true" />
      </Link>
      <nav className="app-nav" aria-label="Primary navigation">
        <Link className={active === "lakes" ? "app-nav__item is-active" : "app-nav__item"} to="/lakes" aria-current={active === "lakes" ? "page" : undefined}>
          Lakes
        </Link>
        <span className={active === "operations" ? "app-nav__item is-active" : "app-nav__item"} aria-current={active === "operations" ? "page" : undefined}>
          Operations
        </span>
        <Link className={active === "profile" ? "app-nav__item is-active" : "app-nav__item"} to="/profile" aria-current={active === "profile" ? "page" : undefined}>
          Profile
        </Link>
      </nav>
      <div className="app-account">
        <div className="app-context">
          <span className="status-dot" aria-hidden="true" />
          <span>{contextLabel ?? "Operator workspace"}</span>
        </div>
        <button className="header-sign-out" type="button" onClick={signOut} disabled={signingOut}>
          {signingOut ? "Signing out…" : "Sign out"}
        </button>
        {signOutError && <span className="header-error" role="alert">{signOutError}</span>}
      </div>
    </header>
  );
}
