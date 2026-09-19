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

      // Convert the percentage selection to screenshot pixels, then snap the
      // crop outward to integer pixel boundaries. Canvas dimensions are integer
      // pixels, so fractional source/destination rectangles can resample edge
      // pixels and make nearly identical selections produce different images.
      const rawLeft = (crop.x / 100) * img.naturalWidth;
      const rawTop = (crop.y / 100) * img.naturalHeight;
      const rawRight = ((crop.x + crop.width) / 100) * img.naturalWidth;
      const rawBottom = ((crop.y + crop.height) / 100) * img.naturalHeight;

      const sourceX = Math.max(0, Math.floor(rawLeft));
      const sourceY = Math.max(0, Math.floor(rawTop));
      const sourceRight = Math.min(img.naturalWidth, Math.ceil(rawRight));
      const sourceBottom = Math.min(img.naturalHeight, Math.ceil(rawBottom));

      const sourceWidth = sourceRight - sourceX;
      const sourceHeight = sourceBottom - sourceY;

      if (sourceWidth <= 0 || sourceHeight <= 0) {
         return;
      }

      canvas.width = sourceWidth;
      canvas.height = sourceHeight;

      const ctx = canvas.getContext("2d");
      if (!ctx) {
         return;
      }

      // Source and destination rectangles are the same integer dimensions.
      // Disable smoothing so this remains a direct screenshot-pixel crop.
      ctx.imageSmoothingEnabled = false;

      ctx.drawImage(
         img,
         sourceX,
         sourceY,
         sourceWidth,
         sourceHeight,
         0,
         0,
         sourceWidth,
         sourceHeight,
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
