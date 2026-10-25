import { lazy, Suspense } from "react";
import { PageLoadBoundary } from "./components/PageLoadBoundary";
import { RouteMetadata } from "./auth/RouteMetadata";
import "./auth/recoverySession";
import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { AuthGate } from "./auth/AuthGate";
import { PrincipalProvider } from "./auth/PrincipalProvider";
import { ActiveStationProvider } from "./hooks/useActiveStation";
import { usePrincipal } from "./auth/PrincipalProvider";
import "./styles.css";

const LoginPage = lazy(() => import("./pages/LoginPage").then((module) => ({ default: module.LoginPage })));
const SignupPage = lazy(() => import("./pages/SignupPage").then((module) => ({ default: module.SignupPage })));
const VerifyOtpPage = lazy(() => import("./pages/VerifyOtpPage").then((module) => ({ default: module.VerifyOtpPage })));
const OnboardingPage = lazy(() => import("./pages/OnboardingPage").then((module) => ({ default: module.OnboardingPage })));
const LakeGridPage = lazy(() => import("./pages/LakeGridPage").then((module) => ({ default: module.LakeGridPage })));
const LakeLiveView = lazy(() => import("./pages/LakeLiveView").then((module) => ({ default: module.LakeLiveView })));
const ProfileSettingsPage = lazy(() => import("./pages/ProfileSettingsPage").then((module) => ({ default: module.ProfileSettingsPage })));
const AlertsPage = lazy(() => import("./pages/AlertsPage").then((module) => ({ default: module.AlertsPage })));
const ReportsPage = lazy(() => import("./pages/ReportsPage").then((module) => ({ default: module.ReportsPage })));
const DronesPage = lazy(() => import("./pages/DronesPage").then((module) => ({ default: module.DronesPage })));
const OfficerVerificationPage = lazy(() => import("./pages/OfficerVerificationPage").then((module) => ({ default: module.OfficerVerificationPage })));
const StationAccessPage = lazy(() => import("./pages/StationAccessPage").then((module) => ({ default: module.StationAccessPage })));
const StationAdminPage = lazy(() => import("./pages/StationAdminPage").then((module) => ({ default: module.StationAdminPage })));
const AddLakePage = lazy(() => import("./pages/AddLakePage").then((module) => ({ default: module.AddLakePage })));
const ReviewConsolePage = lazy(() => import("./pages/ReviewConsolePage").then((module) => ({ default: module.ReviewConsolePage })));
const InvitationAcceptPage = lazy(() => import("./pages/InvitationAcceptPage").then((module) => ({ default: module.InvitationAcceptPage })));
const CivilianHomePage = lazy(() => import("./pages/CivilianHomePage").then((module) => ({ default: module.CivilianHomePage })));

const ForgotPasswordPage = lazy(() => import("./pages/PasswordRecoveryPages").then((module) => ({ default: module.ForgotPasswordPage })));
const ResetPasswordPage = lazy(() => import("./pages/PasswordRecoveryPages").then((module) => ({ default: module.ResetPasswordPage })));

export default function App() {
  return <BrowserRouter><RouteMetadata /><PageLoadBoundary><Suspense fallback={<main className="auth-loading" role="status">Loading LakeSafe...</main>}><Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route path="/forgot-password" element={<ForgotPasswordPage />} />
    <Route path="/reset-password" element={<ResetPasswordPage />} />
    <Route path="/onboarding" element={<OnboardingPage />} />
    <Route path="/signup" element={<SignupPage />} />
    <Route path="/verify-2fa" element={<VerifyOtpPage />} />
    <Route element={<OperatorProviders />}>
      {/* Inside the providers so a signed-in visitor sees their way back instead of Sign in. */}
      <Route path="/" element={<CivilianHomePage />} />
      <Route path="/public" element={<CivilianHomePage />} />
      <Route element={<AuthGate />}>
        <Route path="/lakes" element={<LakeLanding />} />
        <Route element={<OperationalGate />}>
          <Route path="/lakes/:lakeId" element={<LakeLiveView />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="/drones" element={<DronesPage />} />
          <Route path="/drones/setup" element={<DronesPage setup />} />
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
  </Routes></Suspense></PageLoadBoundary></BrowserRouter>;
}

function OperatorProviders() { return <PrincipalProvider><ActiveStationProvider><Outlet /></ActiveStationProvider></PrincipalProvider>; }

function LakeLanding() {
  const { principal, loading, error, refresh } = usePrincipal();
  if (loading) return <main className="auth-loading">Preparing your workspace…</main>;
  if (error) return <main className="auth-page"><section className="auth-card"><h1>We couldn’t load your account</h1><p className="form-error" role="alert">{error}</p><button onClick={() => void refresh()}>Retry</button></section></main>;
  return principal?.account_class === "civilian" ? <CivilianHomePage /> : <LakeGridPage />;
}

function OperationalGate() {
  const { principal, loading } = usePrincipal();
  if (loading) return <main className="auth-loading">Checking operational access…</main>;
  const activeMembership = principal?.memberships.some((item) => item.status === "active");
  return principal?.account_class === "officer" && activeMembership ? <Outlet /> : <Navigate to="/public" replace />;
}
