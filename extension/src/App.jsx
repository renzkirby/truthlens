import { useState } from "react";
import reactLogo from "./assets/react.svg";
import viteLogo from "/vite.svg";
import "./App.css";

function App() {
   const [isSnipping, setIsSnipping] = useState(false);

   const handleSnipClick = async () => {
      setIsSnipping(true);

      try {
         const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

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

   return (
      <div
         className="card"
         style={{ padding: "20px", width: "250px", textAlign: "center" }}>
         <h2>TruthLens</h2>
         <p style={{ fontSize: "12px", color: "gray" }}>Verify claims instantly</p>

         <button
            onClick={handleSnipClick}
            disabled={isSnipping}
            style={{ padding: "10px 20px", cursor: "pointer", marginTop: "10px" }}>
            {isSnipping ? "Snipping..." : "Start Snipping ✂️"}
         </button>
      </div>
   );
}

export default App;
