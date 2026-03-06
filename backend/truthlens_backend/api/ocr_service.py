import easyocr

print("Loading EasyOCR model...")
ocr_reader = easyocr.Reader(["en", "tl"])
print("EasyOCR model loaded successfully!")


def extract_text_from_image(image_bytes):
    ocr_result = ocr_reader.readtext(image_bytes, detail=0)

    if not ocr_result:
        return ""

    extracted_text = " ".join(ocr_result)
    return extracted_text
