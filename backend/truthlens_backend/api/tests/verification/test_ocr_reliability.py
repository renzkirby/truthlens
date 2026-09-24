import base64
import os
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, TestCase

from api import ocr_adapter, ocr_service, tasks
from api.models import Claim
from api.ocr_adapter import OCRProviderUnavailableError


class OCRAdapterReliabilityTests(SimpleTestCase):
    def setUp(self):
        self.image_bytes = b"image fixture"
        self.providers = {"vision": Mock(), "easyocr": Mock()}
        self.metric_hook = Mock()
        self.get_provider = self.enterContext(patch(
            "api.ocr_adapter._get_provider",
            side_effect=lambda name: self.providers[name],
        ))
        self.enterContext(patch("api.ocr_adapter._ocr_metric_hook", self.metric_hook))
        self.enterContext(patch.dict(os.environ, {"OCR_METRICS_ENABLED": "true"}))

    def _extract(self, configuration):
        with patch.dict(os.environ, {"OCR_PROVIDER": configuration}):
            return ocr_adapter.extract_text_with_provider_adapter(self.image_bytes)

    def _assert_terminal_event(self, expected):
        terminal_events = [
            call.args[0]["event"]
            for call in self.metric_hook.call_args_list
            if call.args[0]["event"] in {"ocr.success", "ocr.no_text", "ocr.failed"}
        ]
        self.assertEqual(terminal_events, [expected])

    def test_easyocr_returns_text(self):
        self.providers["easyocr"].extract_text.return_value = "Extracted text"

        self.assertEqual(self._extract("easyocr"), "Extracted text")

        self.providers["easyocr"].extract_text.assert_called_once_with(self.image_bytes)
        self.get_provider.assert_called_once_with("easyocr")
        self._assert_terminal_event("ocr.success")

    def test_easyocr_completed_no_text_returns_empty_string(self):
        self.providers["easyocr"].extract_text.return_value = ""

        self.assertEqual(self._extract("easyocr"), "")

        self._assert_terminal_event("ocr.no_text")

    def test_easyocr_failure_raises_unavailable(self):
        error = RuntimeError("Provider unavailable")
        self.providers["easyocr"].extract_text.side_effect = error

        with self.assertRaises(OCRProviderUnavailableError) as raised:
            self._extract("easyocr")

        self.assertIs(raised.exception.__cause__, error)
        self._assert_terminal_event("ocr.failed")

    def test_vision_failure_falls_back_to_easyocr_text(self):
        self.providers["vision"].extract_text.side_effect = RuntimeError("Unavailable")
        self.providers["easyocr"].extract_text.return_value = "Fallback text"

        self.assertEqual(self._extract("vision_first"), "Fallback text")

        self.assertEqual(
            [call.args[0] for call in self.get_provider.call_args_list],
            ["vision", "easyocr"],
        )
        self._assert_terminal_event("ocr.success")
        self.assertTrue(self.metric_hook.call_args.args[0]["used_fallback"])

    def test_vision_failure_then_easyocr_no_text_is_legitimate(self):
        self.providers["vision"].extract_text.side_effect = RuntimeError("Unavailable")
        self.providers["easyocr"].extract_text.return_value = ""

        self.assertEqual(self._extract("vision_first"), "")

        self._assert_terminal_event("ocr.no_text")

    def test_both_provider_failures_raise_unavailable(self):
        self.providers["vision"].extract_text.side_effect = RuntimeError("Unavailable")
        final_error = RuntimeError("Fallback unavailable")
        self.providers["easyocr"].extract_text.side_effect = final_error

        with self.assertRaises(OCRProviderUnavailableError) as raised:
            self._extract("vision_first")

        self.assertIs(raised.exception.__cause__, final_error)
        self.assertEqual(self.get_provider.call_count, 2)
        self._assert_terminal_event("ocr.failed")

    def test_vision_no_text_then_easyocr_failure_is_legitimate(self):
        self.providers["vision"].extract_text.return_value = ""
        self.providers["easyocr"].extract_text.side_effect = RuntimeError("Unavailable")

        self.assertEqual(self._extract("vision_first"), "")

        self.providers["easyocr"].extract_text.assert_called_once_with(self.image_bytes)
        self._assert_terminal_event("ocr.no_text")

    def test_vision_no_text_continues_to_fallback_text(self):
        self.providers["vision"].extract_text.return_value = ""
        self.providers["easyocr"].extract_text.return_value = "Fallback text"

        self.assertEqual(self._extract("vision_first"), "Fallback text")

        self._assert_terminal_event("ocr.success")

    def test_empty_input_retains_existing_behavior(self):
        self.assertEqual(ocr_adapter.extract_text_with_provider_adapter(b""), "")
        self.get_provider.assert_not_called()
        self.assertEqual(self.metric_hook.call_args.args[0]["event"], "ocr.invalid_input")

    def test_provider_initialization_failure_raises_unavailable(self):
        self.get_provider.side_effect = RuntimeError("Initialization unavailable")

        with self.assertRaises(OCRProviderUnavailableError):
            self._extract("easyocr")

        self._assert_terminal_event("ocr.failed")

    def test_failure_exception_logs_and_metrics_exclude_provider_details(self):
        secret = "private-image-content-and-secret-key"
        for provider in self.providers.values():
            provider.extract_text.side_effect = RuntimeError(secret)

        with self.assertLogs("api.ocr_adapter", level="INFO") as logs:
            with self.assertRaises(OCRProviderUnavailableError) as raised:
                self._extract("vision_first")

        self.assertEqual(
            str(raised.exception),
            "No configured OCR provider successfully completed this request.",
        )
        self.assertNotIn(secret, "\n".join(logs.output))
        self.assertNotIn(secret, repr(self.metric_hook.call_args_list))
        self._assert_terminal_event("ocr.failed")

    def test_service_entry_point_propagates_unavailable(self):
        self.providers["easyocr"].extract_text.side_effect = RuntimeError("Unavailable")
        self.assertIs(ocr_service.OCRProviderUnavailableError, OCRProviderUnavailableError)

        with patch.dict(os.environ, {"OCR_PROVIDER": "easyocr"}):
            with self.assertRaises(OCRProviderUnavailableError):
                ocr_service.extract_text_from_image(self.image_bytes)


class SnippetOCRReliabilityTests(TestCase):
    def setUp(self):
        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.IMAGE,
            media_hash="image-hash",
            claim_fingerprint="img:ocr-reliability",
        )
        self.ocr = self.enterContext(patch("api.tasks.extract_text_from_image"))
        self.deepfake = self.enterContext(patch(
            "api.tasks.detect_ai_image",
            return_value={"score": 0.99, "category": "AI Generated"},
        ))
        self.save_claim = self.enterContext(patch(
            "api.tasks._save_claim", wraps=tasks._save_claim,
        ))
        self.core_pipeline = self.enterContext(patch("api.tasks.execute_core_text_pipeline"))
        self.create_run = self.enterContext(patch("api.tasks.create_verification_run"))
        self.stage = self.enterContext(patch("api.tasks._log_stage", wraps=tasks._log_stage))
        self.enterContext(patch("api.embedding_service.generate_embedding", return_value=None))
        self.media_fetch = self.enterContext(patch(
            "api.tasks.requests.get", side_effect=AssertionError("Unexpected network call"),
        ))

    def _execute(self, *, check_deepfake=False):
        tasks.snippet_fact_check_process.run(
            "image-hash",
            self.claim.pk,
            check_deepfake=check_deepfake,
            base64_string=base64.b64encode(b"image fixture").decode("ascii"),
        )
        self.ocr.assert_called_once_with(b"image fixture")
        self.media_fetch.assert_not_called()
        self.create_run.assert_not_called()

    def _assert_outcome(self, expected):
        terminal_calls = [
            call for call in self.stage.call_args_list
            if call.args[1] == "snippet_task_total"
        ]
        self.assertEqual(len(terminal_calls), 1)
        self.assertEqual(terminal_calls[0].kwargs["outcome"], expected)

    def test_legitimate_no_text_without_deepfake_deletes_claim(self):
        self.ocr.return_value = ""

        self._execute()

        self.assertFalse(Claim.objects.filter(pk=self.claim.pk).exists())
        self.save_claim.assert_not_called()
        self.core_pipeline.assert_not_called()
        self.deepfake.assert_not_called()
        self._assert_outcome("no_text_deleted")

    def test_legitimate_no_text_with_deepfake_preserves_existing_ai_verdict(self):
        self.ocr.return_value = ""

        self._execute(check_deepfake=True)

        self.claim.refresh_from_db()
        self.assertTrue(self.claim.is_ai_generated)
        self.assertEqual(self.claim.ai_verdict, "MISLEADING")
        self.assertIn("contains no verifiable text", self.claim.ai_summary)
        self.assertIsNone(self.claim.final_verdict)
        self.assertFalse(self.claim.verification_runs.exists())
        self.save_claim.assert_called_once()
        self.core_pipeline.assert_not_called()
        self._assert_outcome("no_text_deepfake_verdict")

    def _assert_unavailable_preserves_claim(self, *, check_deepfake):
        self.ocr.side_effect = OCRProviderUnavailableError("OCR providers unavailable")

        with self.assertLogs("api.tasks", level="INFO") as logs:
            self._execute(check_deepfake=check_deepfake)

        self.claim.refresh_from_db()
        self.assertIsNone(self.claim.ai_verdict)
        self.assertIsNone(self.claim.final_verdict)
        self.assertIsNone(self.claim.ai_summary)
        self.assertIsNone(self.claim.ai_reasoning)
        self.assertFalse(self.claim.verification_runs.exists())
        self.save_claim.assert_not_called()
        self.core_pipeline.assert_not_called()
        self._assert_outcome("ocr_unavailable")
        failed_calls = [call for call in self.stage.call_args_list if call.args[1] == "ocr_failed"]
        self.assertEqual(len(failed_calls), 1)
        self.assertEqual(failed_calls[0].kwargs["outcome"], "ocr_unavailable")
        output = "\n".join(logs.output)
        self.assertIn("stage=ocr_failed", output)
        self.assertIn("outcome=ocr_unavailable", output)
        self.assertNotIn("no_text", output)
        self.assertNotIn("contains no verifiable text", output)

    def test_ocr_unavailable_preserves_claim_without_verdict_or_core_pipeline(self):
        self._assert_unavailable_preserves_claim(check_deepfake=False)
        self.deepfake.assert_not_called()

    def test_ocr_unavailable_after_deepfake_detection_avoids_no_text_verdict(self):
        self._assert_unavailable_preserves_claim(check_deepfake=True)
        self.claim.refresh_from_db()
        self.assertTrue(self.claim.is_ai_generated)
        self.deepfake.assert_called_once_with(b"image fixture")

    def test_successful_ocr_hands_text_to_core_pipeline(self):
        self.ocr.return_value = "Extracted text"

        self._execute()

        self.core_pipeline.assert_called_once_with(
            "Extracted text", self.claim.pk, triggered_by_id=None,
        )
        self.assertTrue(Claim.objects.filter(pk=self.claim.pk).exists())
        self.save_claim.assert_not_called()
        self._assert_outcome("completed")
