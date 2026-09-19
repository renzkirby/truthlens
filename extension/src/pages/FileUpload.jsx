import { useState } from "react";
import { UploadCloud, FileText } from "lucide-react";
import "./FileUpload.css";

function FileUpload() {
   const [file, setFile] = useState(null);
   const [isAnalyzing, setIsAnalyzing] = useState(false);

   const handleFileChange = (e) => {
      const selectedFile = e.target.files[0];
      if (selectedFile && (
         selectedFile.type === "text/plain" || 
         selectedFile.type === "application/pdf" || 
         selectedFile.name.toLowerCase().endsWith(".docx")
      )){
         setFile(selectedFile);
      } else {
         alert("Please upload a valid .txt or .pdf file.");
      }
   };

   const handleAnalyzeFile = async () => {
      if (!file) return;

      setIsAnalyzing(true);

      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

      if (!tab || tab.url.startsWith("chrome://") || tab.url.startsWith("edge://") || tab.url.startsWith("about:")) {
         alert("TruthLens cannot display results on Chrome system pages or blank tabs. Please open a normal website and try again!");
         setIsAnalyzing(false);
         return;
      }

      chrome.tabs.sendMessage(tab.id, { 
         type: "DISPLAY_URL_LOADING",
         customMsg: "Extracting text and analyzing claims..." 
      });

      const reader = new FileReader();
      
      reader.onload = (event) => {
         const fileData = event.target.result; 
         
         chrome.runtime.sendMessage(
            {
               type: "VERIFY_FILE", 
               tabId: tab.id, 
               payload: { 
                  file_data: fileData,
                  file_name: file.name,
                  file_type: file.type
               },
            },
            (response) => {
               if (chrome.runtime.lastError || !response?.success) {
                  chrome.tabs.sendMessage(tab.id, { 
                     type: "DISPLAY_SNIPPET_ERROR", 
                     message: "Failed to analyze the file. Please try again." 
                  });
               }
               window.close(); 
            }
         );
      };
 
      // ALWAYS READ AS BASE64
      reader.readAsDataURL(file); 
   };

   return (
      <div className="file-page">
         <div className="page-intro">
            <span className="page-eyebrow">Upload File</span>
            <h1>Investigate a document.</h1>
            <p>Upload a file to analyze its claims.</p>
         </div>
         <div className="file-upload-area">
            <UploadCloud size={32} className="file-upload-icon" aria-hidden="true" />
            <h2>Choose a document</h2>
            <p>Supports .txt and .pdf files</p>
            
            {/* 1. The Hidden Input */}
            <input 
               id="truthlens-file-upload"
               type="file" 
               accept=".txt,.pdf"
               onChange={handleFileChange} 
               className="file-input"
               aria-label="Choose a document to analyze"
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
            type="button"
            className="primary-button"
            onClick={handleAnalyzeFile}
            disabled={!file || isAnalyzing}>
            {isAnalyzing ? "Analyzing..." : "Scan File for Claims"}
         </button>
      </div>
   );
}

export default FileUpload;
