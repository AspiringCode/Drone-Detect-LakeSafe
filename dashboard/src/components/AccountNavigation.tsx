import { Link } from "react-router-dom";
import { useOptionalPrincipal } from "../auth/PrincipalProvider";
import "../pages/website-touchups.css";

export function AccountNavigation({ active }: { active: "profile" | "access" | "stations" }) {
  return <nav className="local-tabs" aria-label="Account settings">{[
    { key: "profile", title: "Profile", path: "/profile" },
    { key: "access", title: "Access", path: "/verify-affiliation" },
    { key: "stations", title: "Stations", path: "/station-access" },
  ].map((item) => <Link key={item.key} to={item.path} className={active === item.key ? "is-active" : ""} aria-current={active === item.key ? "page" : undefined}>{item.title}</Link>)}</nav>;
}

export function AccountStations() {
  const principal = useOptionalPrincipal()?.principal;
  const memberships = principal?.memberships ?? [];
  return <section className="touch-panel" aria-label="Your stations"><h2>Your stations</h2>{!memberships.length ? <p>No station membership yet.</p> : <ul className="coverage-lakes">{memberships.map((membership) => <li key={membership.station_id}><div><strong>{membership.station_name}</strong><p className="membership-status">{membership.status.replace(/_/g, " ")}</p><div className="membership-roles" aria-label={`Roles at ${membership.station_name}`}>{membership.roles.map((role) => <strong key={role}>{role.replace(/_/g, " ").replace(/^./, (letter) => letter.toUpperCase())}</strong>)}</div></div>{membership.status === "active" && membership.capabilities.includes("member.manage") && <Link to={`/stations/${membership.station_id}/admin`}>Manage station</Link>}</li>)}</ul>}</section>;
}
