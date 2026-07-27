import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
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
import "./styles.css";

export default function App() {
  return <PrincipalProvider><ActiveStationProvider><BrowserRouter><Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route path="/signup" element={<SignupPage />} />
    <Route path="/verify-2fa" element={<VerifyOtpPage />} />
    <Route element={<OnboardingGate />}>
      <Route path="/onboarding" element={<OnboardingPage />} />
    </Route>
    <Route element={<AuthGate />}>
      <Route path="/lakes" element={<LakeGridPage />} />
      <Route path="/lakes/:lakeId" element={<LakeLiveView />} />
      <Route path="/profile" element={<ProfileSettingsPage />} />
      <Route path="/alerts" element={<AlertsPage />} />
      <Route path="/reports" element={<ReportsPage />} />
      <Route path="/verify-affiliation" element={<OfficerVerificationPage />} />
      <Route path="/station-access" element={<StationAccessPage />} />
      <Route path="/invitations/accept" element={<InvitationAcceptPage />} />
      <Route path="/stations/:stationId/admin" element={<StationAdminPage />} />
      <Route path="/stations/:stationId/lakes/new" element={<AddLakePage />} />
      <Route path="/internal/reviews" element={<ReviewConsolePage />} />
    </Route>
    <Route path="*" element={<Navigate to="/lakes" replace />} />
  </Routes></BrowserRouter></ActiveStationProvider></PrincipalProvider>;
}
