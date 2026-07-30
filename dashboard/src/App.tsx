import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { AuthGate } from "./auth/AuthGate";
import { OnboardingGate } from "./auth/OnboardingGate";
import { LoginPage } from "./pages/LoginPage";
import { SignupPage } from "./pages/SignupPage";
import { VerifyOtpPage } from "./pages/VerifyOtpPage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { LakeGridPage } from "./pages/LakeGridPage";
import { LakeLiveView } from "./pages/LakeLiveView";
import { ProfileSettingsPage } from "./pages/ProfileSettingsPage";
import { AlertsPage } from "./pages/AlertsPage";
import { ReportsPage } from "./pages/ReportsPage";
import { PrincipalProvider } from "./auth/PrincipalProvider";
import { ActiveStationProvider } from "./hooks/useActiveStation";
import { OfficerVerificationPage } from "./pages/OfficerVerificationPage";
import { StationAccessPage } from "./pages/StationAccessPage";
import { StationAdminPage } from "./pages/StationAdminPage";
import { AddLakePage } from "./pages/AddLakePage";
import { ReviewConsolePage } from "./pages/ReviewConsolePage";
import { InvitationAcceptPage } from "./pages/InvitationAcceptPage";
import { CivilianHomePage } from "./pages/CivilianHomePage";
import { usePrincipal } from "./auth/PrincipalProvider";
import "./styles.css";

export default function App() {
  return <BrowserRouter><Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route path="/signup" element={<SignupPage />} />
    <Route path="/verify-2fa" element={<VerifyOtpPage />} />
    <Route path="/" element={<CivilianHomePage />} />
    <Route path="/public" element={<CivilianHomePage />} />
    <Route element={<OperatorProviders />}>
      <Route element={<OnboardingGate />}><Route path="/onboarding" element={<OnboardingPage />} /></Route>
      <Route element={<AuthGate />}>
        <Route path="/lakes" element={<LakeLanding />} />
        <Route element={<OperationalGate />}>
          <Route path="/lakes/:lakeId" element={<LakeLiveView />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/reports" element={<ReportsPage />} />
        </Route>
        <Route path="/profile" element={<ProfileSettingsPage />} />
        <Route path="/verify-affiliation" element={<OfficerVerificationPage />} />
        <Route path="/station-access" element={<StationAccessPage />} />
        <Route path="/invitations/accept" element={<InvitationAcceptPage />} />
        <Route path="/stations/:stationId/admin" element={<StationAdminPage />} />
        <Route path="/stations/:stationId/lakes/new" element={<AddLakePage />} />
        <Route path="/internal/reviews" element={<ReviewConsolePage />} />
      </Route>
    </Route>
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes></BrowserRouter>;
}

function OperatorProviders() { return <PrincipalProvider><ActiveStationProvider><Outlet /></ActiveStationProvider></PrincipalProvider>; }

function LakeLanding() {
  const { principal, loading } = usePrincipal();
  if (loading) return <main className="auth-loading">Preparing your workspace…</main>;
  return principal?.account_class === "civilian" ? <CivilianHomePage /> : <LakeGridPage />;
}

function OperationalGate() {
  const { principal, loading } = usePrincipal();
  if (loading) return <main className="auth-loading">Checking operational access…</main>;
  const activeMembership = principal?.memberships.some((item) => item.status === "active");
  return principal?.account_class === "officer" && activeMembership ? <Outlet /> : <Navigate to="/public" replace />;
}
