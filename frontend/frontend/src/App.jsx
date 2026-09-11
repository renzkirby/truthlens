import "./App.css";
import LandingPage from "./Pages/LandingPage";
import CommunityFeed from "./Pages/CommunityFeed";
import LoginPage from "./Pages/LoginPage";
import RegisterPage from "./Pages/RegisterPage";
import TruthLensWireframes from "./Pages/wireframe/TruthLens_Wireframes";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import PrivateRoute from "./components/PrivateRoute";
import CreateThreadPage from "./Pages/CreateThreadPage";
import UserProfile from "./Pages/UserProfile.jsx";
import ThreadDetailPage from "./Pages/ThreadDetailPage";
import VerifyPage from "./Pages/VerifyPage.jsx";
import WorkspacePage from "./Pages/WorkspacePage.jsx";
import VerifyEmailPage from "./Pages/VerifyEmailPage.jsx";
import Toast from "./components/Toast";
import UserHub from "./Pages/UserHub.jsx";
import NotificationPage from "./Pages/NotificationPage.jsx";
import SettingsPage from "./Pages/SettingsPage.jsx";
import DeepAnalysisPage from "./Pages/DeepAnalysisPage.jsx";
import OnboardingPage from "./Pages/OnboardingPage.jsx";
import ForgotPasswordPage from "./Pages/ForgotPasswordPage.jsx";
import ResetPasswordPage from "./Pages/ResetPasswordPage.jsx";
import RootRedirect from "./components/RootRedirect";
import OrganizationInvitationPage from "./Pages/OrganizationInvitationPage.jsx";
import PartnersPage from "./Pages/PartnersPage.jsx";
import PartnerProfilePage from "./Pages/PartnerProfilePage.jsx";
import AppShell from "./components/app/AppShell.jsx";
import PublicShell from "./components/public/PublicShell.jsx";
import AccountActionShell from "./components/account/AccountActionShell.jsx";
import OnboardingShell from "./components/account/OnboardingShell.jsx";

function App() {
   return (
      <>
         <Toast />
         <BrowserRouter>
            <Routes>
               <Route element={<PublicShell />}>
                  <Route path="/landing-page" element={<LandingPage />} />
                  <Route path="/partners" element={<PartnersPage />} />
                  <Route path="/partners/:slug" element={<PartnerProfilePage />} />
               </Route>
               <Route path="/login" element={<LoginPage />} />
               <Route path="/register" element={<RegisterPage />} />
               <Route path="/forgot-password" element={<ForgotPasswordPage />} />
               <Route path="/reset-password/:uid/:token" element={<ResetPasswordPage />} />
               <Route path="/" element={<RootRedirect />} />
               <Route path="/wireframes" element={<TruthLensWireframes />} />
               <Route path="/verify-email" element={<VerifyEmailPage />} />
               <Route element={<AccountActionShell />}>
                  <Route path="/organization-invitations/:token" element={<OrganizationInvitationPage />} />
               </Route>

               {/* Protected Routes - accessible to any authenticated user */}
               <Route element={<PrivateRoute />}>
                  <Route element={<OnboardingShell />}>
                     <Route path="/onboarding" element={<OnboardingPage />} />
                  </Route>

                  <Route element={<AppShell />}>
                     <Route path="/community" element={<CommunityFeed />} />
                     <Route path="/dashboard" element={<UserHub />} />
                     <Route path="/verify" element={<VerifyPage />} />
                     <Route path="/thread/create" element={<CreateThreadPage />} />
                     <Route path="/profile" element={<UserProfile />} />
                     <Route path="/thread/detail/:threadId" element={<ThreadDetailPage />} />
                     <Route path="/analysis/:claimId" element={<DeepAnalysisPage />} />
                     <Route path="/user/:username" element={<UserProfile />} />
                     <Route path="/settings" element={<SettingsPage />} />
                     <Route path="/notifications" element={<NotificationPage />} />

                     {/* Capability-driven operational workspace */}
                     <Route element={<PrivateRoute requireWorkspace />}>
                        <Route path="/workspace" element={<WorkspacePage />} />

                        <Route path="/moderation" element={<Navigate to="/workspace" replace />} />
                     </Route>
                  </Route>
               </Route>
            </Routes>
         </BrowserRouter>
      </>
   );
}

export default App;
