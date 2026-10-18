import "./App.css";
import LandingPage from "./Pages/LandingPage";
import CommunityFeed from "./Pages/CommunityFeed";
import LoginPage from "./Pages/LoginPage";
import RegisterPage from "./Pages/RegisterPage";
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
import PublicFactCheckPage from "./Pages/PublicFactCheckPage.jsx";
import AppShell from "./components/app/AppShell.jsx";
import PublicShell from "./components/public/PublicShell.jsx";
import AccountActionShell from "./components/account/AccountActionShell.jsx";
import OnboardingShell from "./components/account/OnboardingShell.jsx";
import WorkspaceShell from "./components/workspace/WorkspaceShell.jsx";
import ManagementRoute from "./components/ManagementRoute.jsx";
import ManagementConsoleShell from "./components/management/ManagementConsoleShell.jsx";
import ManagementOverviewPage from "./Pages/ManagementOverviewPage.jsx";
import ManagementOrganizationsPage from "./Pages/ManagementOrganizationsPage.jsx";
import ManagementOrganizationCreatePage from "./Pages/ManagementOrganizationCreatePage.jsx";
import ManagementOrganizationDetailPage from "./Pages/ManagementOrganizationDetailPage.jsx";
import ManagementMembershipsPage from "./Pages/ManagementMembershipsPage.jsx";
import ManagementMembershipDetailPage from "./Pages/ManagementMembershipDetailPage.jsx";
import ManagementInvitationsPage from "./Pages/ManagementInvitationsPage.jsx";
import ManagementInvitationDetailPage from "./Pages/ManagementInvitationDetailPage.jsx";
import ManagementGovernanceAuditPage from "./Pages/ManagementGovernanceAuditPage.jsx";
import ManagementGovernanceAuditDetailPage from "./Pages/ManagementGovernanceAuditDetailPage.jsx";


function CommunityFactCheckPage() {
   return (
      <div
         style={{
            "--tl-public-gutter-left": "var(--tl-space-6)",
            "--tl-public-gutter-right": "var(--tl-space-6)",
         }}
      >
         <PublicFactCheckPage />
      </div>
   );
}

function App() {
   return (
      <>
         <Toast />
         <BrowserRouter>
            <Routes>
               <Route element={<PublicShell />}>
                  <Route path="/landing" element={<LandingPage />} />
                  <Route path="/landing-page" element={<Navigate to="/landing" replace />} />
                  <Route path="/partners" element={<PartnersPage />} />
                  <Route path="/partners/:slug" element={<PartnerProfilePage />} />
                  <Route path="/partners/:slug/fact-checks/:publicationId" element={<PublicFactCheckPage />} />
               </Route>
               <Route path="/login" element={<LoginPage />} />
               <Route path="/register" element={<RegisterPage />} />
               <Route path="/forgot-password" element={<ForgotPasswordPage />} />
               <Route path="/reset-password/:uid/:token" element={<ResetPasswordPage />} />
               <Route path="/" element={<RootRedirect />} />
               <Route path="/verify-email" element={<VerifyEmailPage />} />
               <Route element={<AccountActionShell />}>
                  <Route path="/organization-invitations/:token" element={<OrganizationInvitationPage />} />
               </Route>

               {/* Protected Routes - accessible to any authenticated user */}
               <Route element={<PrivateRoute />}>
                  <Route element={<ManagementRoute />}>
                     <Route element={<ManagementConsoleShell />}>
                        <Route path="/management" element={<ManagementOverviewPage />} />
                        <Route path="/management/organizations" element={<ManagementOrganizationsPage />} />
                        <Route path="/management/organizations/new" element={<ManagementOrganizationCreatePage />} />
                        <Route
                           path="/management/organizations/:organizationId"
                           element={<ManagementOrganizationDetailPage />}
                        />
                        <Route path="/management/memberships" element={<ManagementMembershipsPage />} />
                        <Route
                           path="/management/memberships/:membershipId"
                           element={<ManagementMembershipDetailPage />}
                        />
                        <Route path="/management/invitations" element={<ManagementInvitationsPage />} />
                        <Route
                           path="/management/invitations/:invitationId"
                           element={<ManagementInvitationDetailPage />}
                        />
                        <Route path="/management/audit" element={<ManagementGovernanceAuditPage />} />
                        <Route
                           path="/management/audit/:eventId"
                           element={<ManagementGovernanceAuditDetailPage />}
                        />
                     </Route>
                  </Route>

                  <Route element={<OnboardingShell />}>
                     <Route path="/onboarding" element={<OnboardingPage />} />
                  </Route>

                  <Route element={<AppShell />}>
                     <Route path="/community" element={<CommunityFeed />} />
                     <Route path="/community/partners/:slug" element={<PartnerProfilePage />} />
                     <Route
                        path="/community/partners/:slug/fact-checks/:publicationId"
                        element={<CommunityFactCheckPage />}
                     />
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
                        <Route element={<WorkspaceShell />}>
                           <Route path="/workspace" element={<WorkspacePage />} />
                           <Route path="/workspace/factual-corrections" element={<WorkspacePage />} />
                           <Route path="/workspace/factual-corrections/:requestId" element={<WorkspacePage />} />
                        </Route>

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
