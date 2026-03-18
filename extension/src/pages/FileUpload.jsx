// FileUpload.jsx
import "./FileUpload.css";
import { Upload } from "lucide-react";

function FileUpload() {
   return (
      <div className="upload-page">
         <div className="drop-zone">
            <div className="upload-icon-wrapper">
               <Upload
                  size={22}
                  color="var(--text-muted)"
                  strokeWidth={1.8}
               />
            </div>
            <div className="upload-title">Drop image or PDF here</div>
            <div className="upload-subtitle">or click to browse files</div>

            <button className="browse-btn">Browse</button>

            {/* Hidden file input for when we wire up the logic later */}
            <input
               type="file"
               className="hidden-file-input"
            />
         </div>
      </div>
   );
}

export default FileUpload;
