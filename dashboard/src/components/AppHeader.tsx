import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { supabase, type SupabaseLike } from "../lib/supabase";
import { useOptionalPrincipal } from "../auth/PrincipalProvider";
import { useOptionalActiveStation } from "../hooks/useActiveStation";

type HeaderSection = "lakes" | "operations" | "alerts" | "reports" | "profile";

type AppHeaderProps = {
  active: HeaderSection;
  contextLabel?: string;
  operationsHref?: string;
  client?: SupabaseLike;
};

export function AppHeader({ active, contextLabel, operationsHref = "/lakes", client = supabase }: AppHeaderProps) {
  const navigate = useNavigate();
  const principalContext = useOptionalPrincipal();
  const activeContext = useOptionalActiveStation();
  const stations = principalContext?.principal?.memberships.filter((membership) => membership.status === "active") ?? [];
  const selectedStation = activeContext?.station?.station_id ?? "";
  const [accountInitial, setAccountInitial] = useState("O");
  const [menuOpen, setMenuOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState("");

  useEffect(() => {
    let current = true;
    if (typeof client.auth?.getUser === "function") {
      void client.auth.getUser().then(({ data }: { data: { user: any } }) => {
        if (!current || !data.user) return;
        const label = data.user.user_metadata?.display_name || data.user.email || "Operator";
        setAccountInitial(label.charAt(0).toUpperCase());
      });
    }
    return () => { current = false; };
  }, [client]);

  function chooseStation(stationId: string) {
    activeContext?.select(stationId);
    navigate("/lakes");
  }

  async function signOut() {
    setSigningOut(true);
    setSignOutError("");
    const { error } = await client.auth.signOut();
    setSigningOut(false);
    if (error) return setSignOutError("Could not sign out. Please try again.");
    window.localStorage.removeItem("lakesafe-active-station");
    navigate("/login", { replace: true });
  }

  const navClass = (section: HeaderSection) => active === section ? "app-nav__item is-active" : "app-nav__item";

  return (
    <header className="app-header">
      <Link className="app-brand" to="/lakes" aria-label="LakeSafe managed lakes">
        <span className="app-brand__name">LakeSafe</span>
        <span className="app-brand__mark" aria-hidden="true" />
      </Link>
      <nav className="app-nav" aria-label="Primary navigation">
        <Link className={navClass("lakes")} to="/lakes" aria-current={active === "lakes" ? "page" : undefined}>Lakes</Link>
        <Link className={navClass("operations")} to={operationsHref} aria-current={active === "operations" ? "page" : undefined}>Operations</Link>
        <Link className={navClass("alerts")} to="/alerts" aria-current={active === "alerts" ? "page" : undefined}>Alerts</Link>
        <Link className={navClass("reports")} to="/reports" aria-current={active === "reports" ? "page" : undefined}>Reports</Link>
      </nav>
      <div className="app-account">
        <label className="station-picker">
          <span className="sr-only">Active station</span>
          <select aria-label="Active station" value={selectedStation} onChange={(event) => chooseStation(event.target.value)}>
            {!stations.length && <option value="">{contextLabel ?? "No active station"}</option>}
            {stations.map((station) => <option value={station.station_id} key={station.station_id}>{station.station_name}</option>)}
          </select>
        </label>
        <button className="account-trigger" type="button" aria-label="Open account menu" aria-expanded={menuOpen} onClick={() => setMenuOpen((open) => !open)}>
          <span aria-hidden="true">{accountInitial}</span>
        </button>
        {menuOpen && (
          <div className="account-menu">
            <Link to="/profile">Profile settings</Link>
            <button type="button" onClick={signOut} disabled={signingOut}>{signingOut ? "Signing out…" : "Sign out"}</button>
            {signOutError && <span className="header-error" role="alert">{signOutError}</span>}
          </div>
        )}
      </div>
    </header>
  );
}
