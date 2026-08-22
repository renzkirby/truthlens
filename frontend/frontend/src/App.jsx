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
import Dashboard from "./Pages/Dashboard.jsx";
import ThreadDetailPage from "./Pages/ThreadDetailPage";
import VerifyPage from "./Pages/VerifyPage.jsx";
import ModerationPage from "./Pages/ModerationPage.jsx";
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

function App() {
   return (
      <>
         <Toast />
         <BrowserRouter>
            <Routes>
               <Route path="/landing-page" element={<LandingPage />} />
               <Route path="/login" element={<LoginPage />} />
               <Route path="/register" element={<RegisterPage />} />
               <Route path="/onboarding" element={<OnboardingPage />} />
               <Route path="/forgot-password" element={<ForgotPasswordPage />} />
               <Route path="/reset-password/:uid/:token" element={<ResetPasswordPage />} />
               <Route path="/" element={<RootRedirect />} />
               <Route path="/wireframes" element={<TruthLensWireframes />} />

               {/* Protected Moderator Page */}
               <Route element={<PrivateRoute requiredRole="MOD" />}>
                  <Route path="/moderation" element={<ModerationPage />} />
               </Route>

               {/* Protected Routes - accessible to any authenticated user */}
               <Route element={<PrivateRoute />}>
                  <Route path="/community" element={<CommunityFeed />} />
                  <Route path="/dashboard" element={<UserHub />} />
                  <Route path="/verify" element={<VerifyPage />} />
                  <Route path="/thread/create" element={<CreateThreadPage />} />
                  <Route path="/profile" element={<UserProfile />} />
                  <Route path="/thread/detail/:threadId" element={<ThreadDetailPage />} />
                  <Route path="/analysis/:claimId" element={<DeepAnalysisPage />} />
                  <Route path="/verify-email" element={<VerifyEmailPage />} />
                  <Route path="/user/:username" element={<UserProfile />} />
                  <Route path="/settings" element={<SettingsPage />} />
                  <Route path="/notifications" element={<NotificationPage />} />
               </Route>
            </Routes>
         </BrowserRouter>
      </>
   );
}

export default App;
