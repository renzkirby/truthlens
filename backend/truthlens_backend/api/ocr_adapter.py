import json
import logging
import os
import time
from typing import Callable, Dict, List, Optional


logger = logging.getLogger(__name__)


MetricHook = Callable[[dict], None]
_ocr_metric_hook: Optional[MetricHook] = None


class OCRProvider:
    name = "base"

    def extract_text(self, image_bytes: bytes) -> str:
        raise NotImplementedError()


class VisionOCRProvider(OCRProvider):
    name = "vision"

    def __init__(self) -> None:
        self._client = None
        self._vision_module = None

    def _get_client(self):
        if self._client is None:
            from google.cloud import vision

            self._vision_module = vision
            self._client = vision.ImageAnnotatorClient()
        return self._client

    def extract_text(self, image_bytes: bytes) -> str:
        client = self._get_client()
        vision = self._vision_module
        image = vision.Image(content=image_bytes)

        mode = os.getenv("OCR_VISION_MODE", "DOCUMENT_TEXT_DETECTION").strip().upper()
        if mode == "TEXT_DETECTION":
            response = client.text_detection(image=image)
            annotations = getattr(response, "text_annotations", None) or []
            text = annotations[0].description if annotations else ""
        else:
            response = client.document_text_detection(image=image)
            full_text = getattr(response, "full_text_annotation", None)
            text = getattr(full_text, "text", "") if full_text else ""

        error = getattr(response, "error", None)
        message = getattr(error, "message", "")
        if message:
            raise RuntimeError(message)

        return (text or "").strip()


class EasyOCRProvider(OCRProvider):
    name = "easyocr"

    def __init__(self) -> None:
        self._reader = None

    def _get_reader(self):
        if self._reader is None:
            import easyocr

            configured_langs = os.getenv("OCR_EASYOCR_LANGS", "en,tl")
            langs = [lang.strip() for lang in configured_langs.split(",") if lang.strip()]
            self._reader = easyocr.Reader(langs or ["en", "tl"])
        return self._reader

    def extract_text(self, image_bytes: bytes) -> str:
        reader = self._get_reader()
        ocr_result = reader.readtext(image_bytes, detail=0)
        if not ocr_result:
            return ""
        return " ".join(ocr_result).strip()


_provider_factories = {
    "vision": VisionOCRProvider,
    "easyocr": EasyOCRProvider,
}
_provider_instances: Dict[str, OCRProvider] = {}


def set_ocr_metric_hook(hook: Optional[MetricHook]) -> None:
    """Register an optional callback to receive OCR metric payloads."""
    global _ocr_metric_hook
    _ocr_metric_hook = hook


def _metrics_enabled() -> bool:
    enabled = os.getenv("OCR_METRICS_ENABLED", "true").strip().lower()
    return enabled not in {"0", "false", "off", "no"}


def _emit_ocr_metric(event: str, **fields: object) -> None:
    if not _metrics_enabled():
        return

    payload = {"event": event, **fields}
    try:
        logger.info(
            "OCR_METRIC %s",
            json.dumps(payload, ensure_ascii=True, sort_keys=True, default=str),
        )
    except Exception:
        logger.info("OCR_METRIC event=%s", event)

    if _ocr_metric_hook is not None:
        try:
            _ocr_metric_hook(payload)
        except Exception as hook_error:
            logger.debug("OCR metric hook raised an error: %s", hook_error)


def _get_provider(provider_name: str) -> OCRProvider:
    provider = _provider_instances.get(provider_name)
    if provider is not None:
        return provider

    provider_factory = _provider_factories.get(provider_name)
    if provider_factory is None:
        raise ValueError(f"Unsupported OCR provider: {provider_name}")

    provider = provider_factory()
    _provider_instances[provider_name] = provider
    return provider


def _get_provider_sequence() -> List[str]:
    """
    Feature flag for OCR provider behavior.

    Supported values for OCR_PROVIDER:
    - vision: only Google Cloud Vision
    - easyocr: only EasyOCR
    - vision_first (default): Vision primary, EasyOCR fallback
    - auto: alias for vision_first
    """
    configured = os.getenv("OCR_PROVIDER", "vision_first").strip().lower()

    if configured in {"vision", "google_vision", "gcv"}:
        return ["vision"]
    if configured in {"easyocr", "easy"}:
        return ["easyocr"]
    if configured in {"vision_first", "auto", "vision_with_fallback", "fallback"}:
        return ["vision", "easyocr"]

    logger.warning("Unknown OCR_PROVIDER '%s'. Falling back to vision_first.", configured)
    return ["vision", "easyocr"]


def extract_text_with_provider_adapter(image_bytes: bytes) -> str:
    """Extract text using configured OCR providers with fallback and metrics hooks."""
    if not image_bytes:
        _emit_ocr_metric("ocr.invalid_input", reason="empty_image_bytes")
        return ""

    configured_provider = os.getenv("OCR_PROVIDER", "vision_first")
    providers = _get_provider_sequence()
    overall_start = time.perf_counter()
    last_error = None

    for attempt_index, provider_name in enumerate(providers, start=1):
        attempt_start = time.perf_counter()
        try:
            provider = _get_provider(provider_name)
            extracted_text = provider.extract_text(image_bytes)
            duration_ms = int((time.perf_counter() - attempt_start) * 1000)

            _emit_ocr_metric(
                "ocr.attempt",
                provider=provider_name,
                configured_provider=configured_provider,
                attempt=attempt_index,
                success=bool(extracted_text),
                duration_ms=duration_ms,
                text_length=len(extracted_text),
            )

            if extracted_text:
                _emit_ocr_metric(
                    "ocr.success",
                    provider=provider_name,
                    configured_provider=configured_provider,
                    used_fallback=attempt_index > 1,
                    total_duration_ms=int((time.perf_counter() - overall_start) * 1000),
                )
                return extracted_text
        except Exception as error:
            last_error = error
            duration_ms = int((time.perf_counter() - attempt_start) * 1000)
            _emit_ocr_metric(
                "ocr.attempt",
                provider=provider_name,
                configured_provider=configured_provider,
                attempt=attempt_index,
                success=False,
                duration_ms=duration_ms,
                error=str(error)[:200],
            )
            logger.warning("OCR provider '%s' failed: %s", provider_name, error)

    _emit_ocr_metric(
        "ocr.failed",
        configured_provider=configured_provider,
        attempted_providers=providers,
        total_duration_ms=int((time.perf_counter() - overall_start) * 1000),
        error=(str(last_error)[:200] if last_error else ""),
    )
    return ""
