import "./App.css";
import LandingPage from "./Pages/LandingPage";
import CommunityFeed from "./Pages/CommunityFeed";
import TruthLensWireframes from "./Pages/wireframe/TruthLens_Wireframes";
import { BrowserRouter, Routes, Route, Link } from "react-router-dom";

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
                  path="/community"
                  element={<CommunityFeed />}
               />
            </Routes>
         </BrowserRouter>
      </>
   );
}

export default App;
