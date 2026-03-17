// UrlUpload.jsx
import { useState } from "react";
import axios from "axios";
import "./UrlUpload.css";
import { Link as LinkIcon, ScanLine, Lightbulb } from "lucide-react";

function UrlUpload() {
   const [url, setUrl] = useState("");
   const [loading, setLoading] = useState(false);
   const [result, setResult] = useState(null);

   const handleVerify = async () => {
      /* ... keep your existing axios logic ... */
   };

   return (
      <div className="url-page">
         <div className="input-label">Paste article or claim URL</div>

         <div className="input-row">
            <div className="url-input-wrapper">
               <LinkIcon
                  size={12}
                  color="#9ca3af"
               />
               <input
                  className="url-input"
                  type="text"
                  placeholder="https://example.com/article..."
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
               />
            </div>
            <button
               className="scan-btn"
               onClick={handleVerify}
               disabled={loading}>
               <ScanLine
                  size={13}
                  strokeWidth={2.5}
               />
               {loading ? "..." : "Scan"}
            </button>
         </div>

         <div className="info-box">
            <Lightbulb
               size={14}
               color="var(--verdict-misleading-border)"
            />
            <p>TruthLens will extract and analyze the main claims from this URL automatically.</p>
         </div>

         {/* Keep your existing {result && (...)} block down here */}
      </div>
   );
}

export default UrlUpload;
