# from .ocr_adapter import extract_text_with_provider_adapter


# def extract_text_from_image(image_bytes):
#     """Backwards-compatible OCR entry point used by the task pipeline."""
#     return extract_text_with_provider_adapter(image_bytes)

from google.cloud import vision
import os

print("Initializing Google Cloud Vision API...")

def extract_text_from_image(image_bytes):
    """
    Takes raw image bytes, sends them to Google Cloud Vision, 
    and returns the extracted text as a single string.
    """
    try:
        # Initialize the client (it automatically looks for your credentials in .env)
        client = vision.ImageAnnotatorClient()
        
        # Load the image bytes into Google's format
        image = vision.Image(content=image_bytes)
        
        # Call the API specifically for document/text detection
        response = client.text_detection(image=image)
        texts = response.text_annotations

        # If it finds no text, return empty string
        if not texts:
            return ""

        # Google returns an array. The very first item (index 0) 
        # is always the neatly formatted combined text of the entire image.
        extracted_text = texts[0].description
        
        # Optional: Catch any errors from Google's side
        if response.error.message:
            print(f"Cloud Vision Error: {response.error.message}")
            return ""
        
        print(f"Extracted Text: {extracted_text[:100]}...")  # Print the first 100 chars for debugging
        return extracted_text

    except Exception as e:
        print(f"OCR Extraction Error: {str(e)}")
        return ""