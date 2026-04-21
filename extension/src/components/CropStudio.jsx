import React, { useState, useRef } from "react";
import ReactCrop from "react-image-crop";
import "react-image-crop/dist/ReactCrop.css";
import "./CropStudio.css";

export default function CropStudio({ imageSrc, onConfirm, onCancel }) {
   const [crop, setCrop] = useState({
      unit: "%", // Percentage in UI
      width: 50,
      height: 50,
      x: 25,
      y: 25,
   });
   const imgRef = useRef(null);

   const generateCroppedImage = async () => {
      const img = imgRef.current;
      if (!img || !crop.width || !crop.height) {
         onCancel();
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
            <h3>Crop Check</h3>
            <p>Select the claim you want to verify</p>
         </div>
         <div className="crop-studio-editor">
            {imageSrc ? (
               <ReactCrop
                  crop={crop}
                  onChange={(pixelCrop, percentCrop) => setCrop(percentCrop)}>
                  <img
                     ref={imgRef}
                     src={imageSrc}
                     onLoad={(e) => {
                        setCrop({
                           unit: "%",
                           width: 50,
                           height: 50,
                           x: 25,
                           y: 25,
                        });
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
               className="crop-btn cancel"
               onClick={onCancel}>
               Cancel
            </button>
            <button
               className="crop-btn confirm"
               onClick={generateCroppedImage}>
               Confirm
            </button>
         </div>
      </div>
   );
}
