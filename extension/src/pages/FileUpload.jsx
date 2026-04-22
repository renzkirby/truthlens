import React, { useState } from "react";
import { UploadCloud } from "lucide-react";
import { displayLoadingCard, displayResultCard, displayErrorCard, removeLoadingCard } from "../modules/ui.jsx";
import { state } from "../modules/state.js";
import "./FileUpload.css";

function FileUpload() {
   const [file, setFile] = useState(null);
   const [isAnalyzing, setIsAnalyzing] = useState(false);

   const handleFileChange = (e) => {
      const selectedFile = e.target.files[0];
      if (selectedFile && (selectedFile.type === "text/plain" || selectedFile.type === "application/pdf")) {
         setFile(selectedFile);
      } else {
         alert("Please upload a valid .txt or .pdf file.");
      }
   };

   const handleAnalyzeFile = async () => {
      if (!file) return;

      setIsAnalyzing(true);

      // 1. Get the active tab
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

      // 2. SAFETY CHECK: Prevent silent failures on restricted pages
      if (!tab || tab.url.startsWith("chrome://") || tab.url.startsWith("edge://") || tab.url.startsWith("about:")) {
         alert("TruthLens cannot display results on Chrome system pages or blank tabs. Please open a normal website and try again!");
         setIsAnalyzing(false);
         return;
      }

      // 3. Tell the content.js in the active tab to show the loading spinner
      chrome.tabs.sendMessage(tab.id, { 
         type: "DISPLAY_URL_LOADING",
         customMsg: "Extracting text and analyzing claims..." 
      });

      const reader = new FileReader();
      
      reader.onload = (event) => {
         const fileData = event.target.result; 
         const isPDF = file.type === "application/pdf";
         
         const messageType = isPDF ? "VERIFY_FILE_PDF" : "VERIFY_FILE_TEXT";
         const payloadKey = isPDF ? "pdf_data" : "text";

         chrome.runtime.sendMessage(
            {
               type: messageType,
               tabId: tab.id, 
               payload: { [payloadKey]: fileData },
            },
            (response) => {
               if (chrome.runtime.lastError || !response?.success) {
                  chrome.tabs.sendMessage(tab.id, { 
                     type: "DISPLAY_SNIPPET_ERROR", 
                     message: "Failed to analyze the file. Please try again." 
                  });
               }
               // Close the popup so the user can watch the loading card on the main page
               window.close(); 
            }
         );
      };
 
      if (file.type === "application/pdf") {
         reader.readAsDataURL(file); 
      } else {
         reader.readAsText(file); 
      }
   };

   return (
      <div style={{ padding: "20px", textAlign: "center" }}>
         <div style={{ border: "2px dashed #d1d5db", borderRadius: "10px", padding: "30px", marginBottom: "20px", backgroundColor: "#f9fafb" }}>
            <UploadCloud size={40} color="#4f46e5" style={{ marginBottom: "10px" }} />
            <h3 style={{ margin: "0 0 10px 0", color: "#374151" }}>Upload Document</h3>
            <p style={{ fontSize: "12px", color: "#6b7280", marginBottom: "15px" }}>Currently supporting .txt and .pdf files</p>
            
            {/* 1. The Hidden Input */}
            <input 
               id="truthlens-file-upload"
               type="file" 
               accept=".txt,.pdf"
               onChange={handleFileChange} 
               className="hidden-input"
            />

            {/* 2. The Custom Button that triggers the hidden input */}
            <label htmlFor="truthlens-file-upload" className="custom-browse-btn">
               {file ? "Change File" : "Browse Files"}
            </label>

            {/* 3. The File Name Display */}
            {file && (
               <div className="selected-file-display">
                  <FileText size={14} color="#4f46e5" />
                  <span className="file-name-text">
                     {file.name}
                  </span>
               </div>
            )}
         </div>

         <button
            onClick={handleAnalyzeFile}
            disabled={!file || isAnalyzing}
            style={{
               width: "100%",
               padding: "10px",
               backgroundColor: file && !isAnalyzing ? "#4f46e5" : "#9ca3af",
               color: "white",
               border: "none",
               borderRadius: "8px",
               fontWeight: "bold",
               cursor: file && !isAnalyzing ? "pointer" : "not-allowed"
            }}>
            {isAnalyzing ? "Analyzing..." : "Scan File for Claims"}
         </button>
      </div>
   );
}

export default FileUpload;