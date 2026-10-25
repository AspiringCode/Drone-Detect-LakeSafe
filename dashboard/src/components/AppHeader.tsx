import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { supabase, type SupabaseLike } from "../lib/supabase";
import { useOptionalPrincipal } from "../auth/PrincipalProvider";
import { useOptionalActiveStation } from "../hooks/useActiveStation";
import { WaveMark } from "./WaveMark";
import { StationPicker } from "./StationPicker";

type HeaderSection = "lakes" | "alerts" | "reports" | "drones" | "profile";

type AppHeaderProps = {
  active: HeaderSection;
  contextLabel?: string;
  showStationPicker?: boolean;
  client?: SupabaseLike;
};

export function AppHeader({ active, contextLabel, showStationPicker = false, client = supabase }: AppHeaderProps) {
  const navigate = useNavigate();
  const principalContext = useOptionalPrincipal();
  const activeContext = useOptionalActiveStation();
  const stations = principalContext?.principal?.memberships?.filter((membership) => membership.status === "active") ?? [];
  const [accountInitial, setAccountInitial] = useState("O");
  const [menuOpen, setMenuOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState("");

  useEffect(() => {
    const target = document.querySelector<HTMLElement>("main > section");
    if (target && !target.id) { target.id = "main-content"; target.tabIndex = -1; }
  }, []);

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

  async function signOut() {
    setSigningOut(true);
    setSignOutError("");
    const { error } = await client.auth.signOut();
    setSigningOut(false);
    if (error) return setSignOutError("Could not sign out. Please try again.");
    window.localStorage.removeItem("lakesafe-active-station");
    navigate("/", { replace: true });
  }

  const navClass = (section: HeaderSection) => active === section ? "app-nav__item is-active" : "app-nav__item";

  return (
    <header className="app-header">
      <a className="skip-link" href="#main-content" onClick={(event) => {
        const target = document.querySelector<HTMLElement>("main > section");
        if (target) { event.preventDefault(); target.id = "main-content"; target.tabIndex = -1; target.focus(); }
      }}>Skip to main content</a>
      <Link className="app-brand" to="/lakes" aria-label="LakeSafe managed lakes">
        <span className="app-brand__name">LakeSafe</span>
        <WaveMark />
      </Link>
      <nav className="app-nav" aria-label="Primary navigation">
        <Link className={navClass("lakes")} to="/lakes" aria-current={active === "lakes" ? "page" : undefined}>Lakes</Link>
        <Link className={navClass("alerts")} to="/alerts" aria-current={active === "alerts" ? "page" : undefined}>Alerts</Link>
        <Link className={navClass("reports")} to="/reports" aria-current={active === "reports" ? "page" : undefined}>Reports</Link>
        {stations.some((station) => station.capabilities.includes("inventory.manage")) && <Link className={navClass("drones")} to="/drones" aria-current={active === "drones" ? "page" : undefined}>Drones</Link>}
      </nav>
      <div className="app-account">
        {principalContext?.principal?.judge_demo_access === true && <span className="status-label">Demo</span>}
        {showStationPicker && <StationPicker contextLabel={contextLabel}/>}
        <button className="account-trigger" type="button" aria-label="Open account menu" aria-expanded={menuOpen} onClick={() => setMenuOpen((open) => !open)}>
          <span aria-hidden="true">{accountInitial}</span>
        </button>
        {menuOpen && (
          <div className="account-menu">
            <Link to="/">Public view</Link>
            <Link to="/profile">Profile settings</Link>
            <Link to="/station-access">Station access</Link>
            {activeContext?.station?.status === "active" && activeContext.station.capabilities.includes("member.manage") && <Link to={`/stations/${activeContext.station.station_id}/admin`}>Station administration</Link>}
            {principalContext?.principal?.reviewer && <Link to="/internal/reviews">LakeSafe review</Link>}
            <button type="button" onClick={signOut} disabled={signingOut}>{signingOut ? "Signing out…" : "Sign out"}</button>
            {signOutError && <span className="header-error" role="alert">{signOutError}</span>}
          </div>
        )}
      </div>
    </header>
  );
}
