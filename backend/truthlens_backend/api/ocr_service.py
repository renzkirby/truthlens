from .ocr_adapter import extract_text_with_provider_adapter


def extract_text_from_image(image_bytes):
    """Backwards-compatible OCR entry point used by the task pipeline."""
    return extract_text_with_provider_adapter(image_bytes)