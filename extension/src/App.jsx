// App.jsx
import { useState, useEffect } from "react";
import "./App.css";
import truthlensIcon from "./assets/truthlens-icon.png";
import NavigationBar from "./components/NavigationBar";
import FileUpload from "./pages/FileUpload";
import SnippingTool from "./pages/SnippingTool";
import UrlUpload from "./pages/UrlUpload";
import { Search } from "lucide-react";

function App() {
   const [isSnipping, setIsSnipping] = useState(false);
   const [activeLink, setActiveLink] = useState("snipping");
   const [checkDeepfake, setCheckDeepfake] = useState(false); 

   // load checkDeepfake choice from switch
   useEffect(() => {
      if (typeof chrome !== "undefined" && chrome.storage) {
         chrome.storage.local.get(["checkDeepfake"], (result) => {
            if (result.checkDeepfake !== undefined) {
               setCheckDeepfake(result.checkDeepfake);
            }
         });
      }
   }, []);

   const handleToggleDeepfake = (checked) => {
      setCheckDeepfake(checked);
      if (typeof chrome !== "undefined" && chrome.storage) {
         chrome.storage.local.set({ checkDeepfake: checked });
      }
   };

   const handleSnipClick = async () => {
      setIsSnipping(true);
      if (typeof chrome === "undefined" || !chrome.tabs) {
         console.error("Chrome Extension API not found.");
         setIsSnipping(false);
         return;
      }
      try {
         const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
         chrome.tabs.sendMessage(tab.id, { type: "ACTIVATE_SNIPPING" }, (response) => {
            if (chrome.runtime.lastError) {
               setIsSnipping(false);
               return;
            }
         });
      } catch (error) {
         setIsSnipping(false);
      }
   };

   const renderContent = () => {
      switch (activeLink) {
         case "snipping":
            return (
               <SnippingTool
                  handleSnipClick={handleSnipClick}
                  isSnipping={isSnipping}
                  checkDeepfake={checkDeepfake}
                  onToggleDeepfake={handleToggleDeepfake}
               />
            );
         case "file-upload":
            return <FileUpload />;
         case "url-upload":
            return <UrlUpload />;
         default:
            return null;
      }
   };

   return (
      <div className="card">
         <div className="header-row">
            <div className="logo-container">
               <div className="logo-box">
                  <img 
                     src={truthlensIcon} 
                     alt="TruthLens" 
                     style={{ width: "25px", height: "25px", objectFit: "contain" }} 
                  />
               </div>
               <h2>TruthLens</h2>
            </div>
            <span className="version-badge">v1.1</span>
         </div>

         <NavigationBar
            activeLink={activeLink}
            setActiveLink={setActiveLink}
         />

         <div className="content-area">{renderContent()}</div>

         <div className="app-footer">
            <span className="footer-user">
               Signed in as <strong>@user</strong>
            </span>
            <a
               href="http://localhost:5174/dashboard"
               className="footer-link">
               Open Web Dashboard &rarr;
            </a>
         </div>
      </div>
   );
}

export default App;
