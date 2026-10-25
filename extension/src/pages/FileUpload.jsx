import { useState } from "react";
import { FileText, Image as ImageIcon, UploadCloud } from "lucide-react";
import "./FileUpload.css";

const DOCUMENT_EXTENSIONS = new Set(["txt", "pdf", "docx"]);
const IMAGE_EXTENSIONS = new Set(["jpg", "jpeg", "png", "webp"]);
const IMAGE_MIME_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

function getExtension(fileName = "") {
   return fileName.split(".").pop()?.toLowerCase() || "";
}

function getUploadKind(file) {
   if (!file) return null;

   const extension = getExtension(file.name);
   if (IMAGE_MIME_TYPES.has(file.type) || IMAGE_EXTENSIONS.has(extension)) return "image";
   if (
      file.type === "text/plain" ||
      file.type === "application/pdf" ||
      DOCUMENT_EXTENSIONS.has(extension)
   ) {
      return "document";
   }

   return null;
}

function FileUpload() {
   const [file, setFile] = useState(null);
   const [uploadKind, setUploadKind] = useState(null);
   const [error, setError] = useState("");
   const [isAnalyzing, setIsAnalyzing] = useState(false);

   const handleFileChange = (event) => {
      const selectedFile = event.target.files?.[0] || null;
      const kind = getUploadKind(selectedFile);

      if (!selectedFile || !kind) {
         setFile(null);
         setUploadKind(null);
         setError("Choose a PDF, DOCX, TXT, JPG, PNG, or WEBP file.");
         event.target.value = "";
         return;
      }

      setFile(selectedFile);
      setUploadKind(kind);
      setError("");
   };

   const handleAnalyzeFile = async () => {
      if (!file || !uploadKind || isAnalyzing) return;

      setIsAnalyzing(true);
      setError("");

      try {
         const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

         if (
            !tab ||
            !Number.isInteger(tab.id) ||
            tab.url?.startsWith("chrome://") ||
            tab.url?.startsWith("edge://") ||
            tab.url?.startsWith("about:")
         ) {
            setError("Open a normal webpage first so TruthLens has somewhere to display the result.");
            setIsAnalyzing(false);
            return;
         }

         chrome.tabs.sendMessage(tab.id, {
            type: "DISPLAY_URL_LOADING",
            customMsg:
               uploadKind === "image"
                  ? "Reading the image and analyzing its claims..."
                  : "Extracting document text and analyzing claims...",
         });

         const reader = new FileReader();

         reader.onerror = () => {
            setIsAnalyzing(false);
            setError("TruthLens could not read that file. Please choose it again.");
         };

         reader.onload = (readerEvent) => {
            const fileData = readerEvent.target?.result;
            if (typeof fileData !== "string") {
               setIsAnalyzing(false);
               setError("TruthLens could not read that file. Please choose it again.");
               return;
            }

            const isImage = uploadKind === "image";
            chrome.runtime.sendMessage(
               {
                  type: isImage ? "VERIFY_IMAGE" : "VERIFY_FILE",
                  tabId: tab.id,
                  payload: isImage
                     ? { image_data: fileData }
                     : {
                          file_data: fileData,
                          file_name: file.name,
                          file_type: file.type,
                       },
               },
               (response) => {
                  if (chrome.runtime.lastError || !response?.accepted) {
                     chrome.tabs.sendMessage(tab.id, {
                        type: isImage ? "DISPLAY_IMAGE_ERROR" : "DISPLAY_SNIPPET_ERROR",
                        message: isImage
                           ? "Failed to analyze the image. Please try again."
                           : "Failed to analyze the document. Please try again.",
                     });
                  }
                  window.close();
               },
            );
         };

         reader.readAsDataURL(file);
      } catch (submissionError) {
         console.error("Upload verification failed:", submissionError);
         setError("TruthLens could not start this analysis. Please try again.");
         setIsAnalyzing(false);
      }
   };

   const SelectedIcon = uploadKind === "image" ? ImageIcon : FileText;

   return (
      <div className="file-page">
         <div className="page-intro">
            <span className="page-eyebrow">Upload Content</span>
            <h1>Investigate an image or document.</h1>
            <p>Upload content to extract and verify factual claims.</p>
         </div>

         <div className="file-upload-area">
            <UploadCloud size={32} className="file-upload-icon" aria-hidden="true" />
            <h2>Choose an image or document</h2>
            <p>PDF, DOCX, TXT, JPG, PNG, or WEBP</p>

            <input
               id="truthlens-file-upload"
               type="file"
               accept=".pdf,.docx,.txt,.jpg,.jpeg,.png,.webp,application/pdf,text/plain,image/jpeg,image/png,image/webp"
               onChange={handleFileChange}
               className="file-input"
               aria-label="Choose an image or document to analyze"
            />

            <label htmlFor="truthlens-file-upload" className="custom-browse-btn">
               {file ? "Change File" : "Browse Files"}
            </label>

            {file && (
               <div className="selected-file-display">
                  <SelectedIcon size={14} aria-hidden="true" />
                  <div className="selected-file-copy">
                     <span className="file-name-text">{file.name}</span>
                     <small>{uploadKind === "image" ? "Image claim verification" : "Document claim verification"}</small>
                  </div>
               </div>
            )}
         </div>

         {error && (
            <p className="file-upload-error" role="alert">
               {error}
            </p>
         )}

         <p className="file-upload-note">
            Uploading an image verifies claims visible in it. To check whether an image may be AI-generated, use
            Deepfake Detection.
         </p>

         <button
            type="button"
            className="primary-button"
            onClick={handleAnalyzeFile}
            disabled={!file || !uploadKind || isAnalyzing}
         >
            {isAnalyzing ? "Analyzing..." : uploadKind === "image" ? "Verify Image Claims" : "Verify Document Claims"}
         </button>
      </div>
   );
}

export default FileUpload;
