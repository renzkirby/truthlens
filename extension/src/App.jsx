import { useState } from "react";
import reactLogo from "./assets/react.svg";
import viteLogo from "/vite.svg";
import "./App.css";
import NavigationBar from "./components/NavigationBar";
import FileUpload from "./pages/FileUpload";
import SnippingTool from "./pages/SnippingTool";
import UrlUpload from "./pages/UrlUpload";
import verifyIcon from "./assets/truthlens-icon.png";

function App() {
   const [isSnipping, setIsSnipping] = useState(false);
   const [activeLink, setActiveLink] = useState("snipping");

   const handleSnipClick = async () => {
      setIsSnipping(true);

      if (typeof chrome === "undefined" || !chrome.tabs) {
         console.error("Chrome Extension API not found. Are you running this as an extension?");
         setIsSnipping(false);
         return;
      }

      try {
         const [tab] = await chrome.tabs.query({
            active: true,
            currentWindow: true,
         });

         chrome.tabs.sendMessage(tab.id, { type: "ACTIVATE_SNIPPING" }, (response) => {
            if (chrome.runtime.lastError) {
               console.error("Could not connect to the page. Try refreshing it.");
               setIsSnipping(false);
               return;
            }

            if (response && response.success) {
               console.log("Snipping mode activated sucessfully!");
               window.close();
            }
         });
      } catch (error) {
         console.error("Error finding active tab:", error);
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
               />
            );
         case "file-upload":
            return (
               <div className="file-upload-page">
                  <FileUpload />
               </div>
            );
         case "url-upload":
            return (
               <div className="url-upload-page">
                  <UrlUpload />
               </div>
            );
         default:
            return null;
      }
   };

   const handleClose = () => {
      window.close();
   };

   return (
      <div className="card">
         <div className="header-row">
            <h2>TruthLens</h2>
            <div className="window-dots">
               <span className="dot red"></span>
               <span className="dot orange"></span>
               <span className="dot green"></span>
               <span
                  className="close-x"
                  onClick={handleClose}>
                  ✕
               </span>
            </div>
         </div>

         <NavigationBar
            activeLink={activeLink}
            setActiveLink={setActiveLink}
         />
         {renderContent()}
      </div>
   );
}

export default App;
