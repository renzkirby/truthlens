import { useState } from "react";
import reactLogo from "./assets/react.svg";
import viteLogo from "/vite.svg";
import "./App.css";

function App() {
  const [isSnipping, setIsSnipping] = useState(false);

  const handleSnipClick = async () => {
    setIsSnipping(true);

    if (typeof chrome === "undefined" || !chrome.tabs) {
      console.error(
        "Chrome Extension API not found. Are you running this as an extension?",
      );
      setIsSnipping(false);
      return;
    }

    try {
      const [tab] = await chrome.tabs.query({
        active: true,
        currentWindow: true,
      });

      chrome.tabs.sendMessage(
        tab.id,
        { type: "ACTIVATE_SNIPPING" },
        (response) => {
          if (chrome.runtime.lastError) {
            console.error("Could not connect to the page. Try refreshing it.");
            setIsSnipping(false);
            return;
          }

          if (response && response.success) {
            console.log("Snipping mode activated sucessfully!");
            window.close();
          }
        },
      );
    } catch (error) {
      console.error("Error finding active tab:", error);
      setIsSnipping(false);
    }
  };

  return (
    <div className="card">
      <div className="header-row">
        <h2>TruthLens</h2>
        <div className="window-dots">
          <span className="dot red"></span>
          <span className="dot orange"></span>
          <span className="dot green"></span>
          <span className="close-x">✕</span>
        </div>
      </div>

      <div className="gray-placeholder"></div>

      {/* WAG GALAWIN! - Original Button Code */}
      <button
        className="snip-btn"
        onClick={handleSnipClick}
        disabled={isSnipping}
        style={{ padding: "10px 20px", cursor: "pointer", marginTop: "10px" }}
      >
        {isSnipping ? "Snipping..." : "Verify"}
        <span className="icon">🔍</span>
      </button>
    </div>
  );
}

export default App;
