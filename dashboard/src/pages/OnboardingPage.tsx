import { Navigate } from "react-router-dom";
/** Compatibility route for previously shared onboarding links. */
export function OnboardingPage() { return <Navigate to="/station-access" replace />; }
