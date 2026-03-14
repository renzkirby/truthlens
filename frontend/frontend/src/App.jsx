import "./App.css";
import LandingPage from "./Pages/LandingPage";
import CommunityFeed from "./Pages/CommunityFeed";
import LoginPage from "./Pages/LoginPage";
import RegisterPage from "./Pages/RegisterPage";
import TruthLensWireframes from "./Pages/wireframe/TruthLens_Wireframes";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import PrivateRoute from "./components/PrivateRoute";

function App() {
   return (
      <>
         <BrowserRouter>
            <Routes>
               <Route
                  path="/landing-page"
                  element={<LandingPage />}
               />
               <Route
                  path="/login"
                  element={<LoginPage />}
               />
               <Route
                  path="/register"
                  element={<RegisterPage />}
               />
               <Route
                  path="/"
                  element={<Navigate to="/login" />}
               />

               <Route element={<PrivateRoute />}>
                  <Route
                     path="/community"
                     element={<CommunityFeed />}
                  />
               </Route>
            </Routes>
         </BrowserRouter>
      </>
   );
}

export default App;
