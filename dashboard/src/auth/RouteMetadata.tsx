import { useEffect } from "react";
import { useLocation } from "react-router-dom";
const metadata: Array<[RegExp, string, string]> = [
  [/^\/(public)?$/, "Public lake notices", "Browse public lake notices and safety information without an account."],
  [/^\/login$/, "Sign in", "Sign in to your LakeSafe account and station workspace."],
  [/^\/signup$/, "Create an account", "Create a LakeSafe account to request verified station access."],
  [/^\/verify-2fa$/, "Verify your authenticator", "Verify your authenticator to continue securely to LakeSafe."],
  [/^\/forgot-password$/, "Reset your password", "Request a secure LakeSafe password reset link."],
  [/^\/reset-password$/, "Choose a new password", "Choose a new LakeSafe password using your recovery link."],
  [/^\/lakes$/, "Lakes", "View the lakes available to your LakeSafe account."],
  [/^\/lakes\//, "Lake lookout", "View authorized lake coverage, detections and fleet status."],
  [/^\/alerts$/, "Alerts", "Review lake detections available to your station."],
  [/^\/reports$/, "Reports", "Review detection totals and lake reports for your station."],
  [/^\/drones\/setup$/, "Drone setup", "Register, assign and connect station drones."],
  [/^\/drones$/, "Drones", "Manage station drone inventory and mission preparation."],
  [/^\/profile$/, "Account settings", "Manage your LakeSafe account and authentication settings."],
  [/^\/verify-affiliation$/, "Verify agency affiliation", "Request verification of your law-enforcement agency affiliation."],
  [/^\/(station-access|onboarding)$/, "Station access", "Request and track access to a verified LakeSafe station."],
  [/^\/invitations\/accept$/, "Accept station invitation", "Review and accept your LakeSafe station invitation."],
  [/^\/stations\/[^/]+\/admin$/, "Station administration", "Manage your authorized station settings and team access."],
  [/^\/stations\/[^/]+\/lakes\/new$/, "Add a lake", "Preview an official shoreline and request lake setup for your station."],
  [/^\/internal\/reviews$/, "Verification reviews", "Review agency and station verification requests with authorized reviewer access."],
];
export function RouteMetadata() {
  const { pathname } = useLocation();
  useEffect(() => {
    const entry = metadata.find(([pattern]) => pattern.test(pathname));
    document.title = `${entry?.[1] ?? "Lake notices"} | LakeSafe`;
    let description = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    if (!description) { description = document.createElement("meta"); description.name = "description"; document.head.append(description); }
    description.content = entry?.[2] ?? "LakeSafe public lake information and verified station workspace.";
  }, [pathname]);
  return null;
}
