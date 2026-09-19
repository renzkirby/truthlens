import { useState, useRef } from "react";
import ReactCrop from "react-image-crop";
import "@fontsource-variable/mona-sans/wght.css";
import "react-image-crop/dist/ReactCrop.css";
import "./CropStudio.css";

export default function CropStudio({ imageSrc, onConfirm, onCancel }) {
   const [crop, setCrop] = useState();
   const imgRef = useRef(null);
   const hasValidCrop = Boolean(crop && crop.width > 0 && crop.height > 0);

   const generateCroppedImage = async () => {
      const img = imgRef.current;
      if (!img || !hasValidCrop) {
         return;
      }

      const canvas = document.createElement("canvas");

      // When unit is '%', the x, y, width, height are percentages of natural size
      // The naturalWidth includes any device pixel ratio applied when the screenshot was taken
      const naturalWidthCrop = (crop.width / 100) * img.naturalWidth;
      const naturalHeightCrop = (crop.height / 100) * img.naturalHeight;
      const naturalXCrop = (crop.x / 100) * img.naturalWidth;
      const naturalYCrop = (crop.y / 100) * img.naturalHeight;

      canvas.width = naturalWidthCrop;
      canvas.height = naturalHeightCrop;

      const ctx = canvas.getContext("2d");
      ctx.imageSmoothingQuality = "high";

      ctx.drawImage(
         img,
         naturalXCrop,
         naturalYCrop,
         naturalWidthCrop,
         naturalHeightCrop,
         0,
         0,
         naturalWidthCrop,
         naturalHeightCrop,
      );

      const croppedDataUrl = canvas.toDataURL("image/png");
      onConfirm(croppedDataUrl);
   };

   return (
      <div className="crop-studio">
         <div className="crop-studio-header">
            <h3>TruthLens · Select content</h3>
            <p>{hasValidCrop ? "Move or resize your selection, then click Confirm." : "Drag across the image to select content to investigate."}</p>
         </div>
         <div className="crop-studio-editor">
            {imageSrc ? (
               <ReactCrop
                  crop={crop}
                  keepSelection
                  onChange={(pixelCrop, percentCrop) => setCrop(percentCrop)}>
                  <img
                     ref={imgRef}
                     src={imageSrc}
                     onLoad={() => {
                        setCrop(undefined);
                     }}
                     alt="Crop source"
                     className="crop-studio-img"
                  />
               </ReactCrop>
            ) : (
               <div className="crop-studio-loading">Loading...</div>
            )}
         </div>
         <div className="crop-studio-actions">
            <button
               type="button"
               className="crop-btn cancel"
               onClick={onCancel}>
               Cancel
            </button>
            <button
               type="button"
               disabled={!hasValidCrop}
               className="crop-btn confirm"
               onClick={generateCroppedImage}>
               Confirm
            </button>
         </div>
      </div>
   );
}
