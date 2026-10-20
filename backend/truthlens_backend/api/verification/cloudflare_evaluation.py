"""Opt-in, development-only Cloudflare Workers AI model evaluation.

Not imported by the live factual-verification provider router. Never logs
prompts, evidence, responses, credentials or vendor error bodies.
"""
import os
import re

import requests


DEFAULT_MODEL = "@cf/google/gemma-4-26b-a4b-it"
ACCOUNT_ID_PATTERN = re.compile(r"^[a-fA-F0-9]{32}$")


class CloudflareEvaluationError(RuntimeError):
    """Sanitized provider failure during a development-only comparison."""


# Only known adapter-generated codes may appear in logs or run telemetry.
# Never forward exception bodies, raw HTTP responses or credential-bearing URLs.
_SAFE_CLOUDFLARE_ERROR_CODES = frozenset({
    "MISSING_OR_INVALID_ACCOUNT_ID",
    "MISSING_API_TOKEN",
    "INVALID_PROMPT",
    "PROMPT_TOO_LONG",
    "UNAPPROVED_MODEL",
    "INVALID_COMPLETION_BUDGET",
    "INVALID_AUDIT_METADATA",
    "INVALID_PROVIDER_RESPONSE",
    "INVALID_EVALUATION_JSON",
    "EMPTY_PROVIDER_RESPONSE",
})
_SAFE_TRANSPORT_ERROR_TYPES = frozenset({
    "ReadTimeout", "ConnectTimeout", "Timeout", "ConnectionError",
    "SSLError", "ProxyError", "TooManyRedirects", "HTTPError",
    "RequestException", "ChunkedEncodingError",
})


def sanitized_cloudflare_error_code(error):
    """Return a strict, bounded error category; never leak vendor error text."""
    if not isinstance(error, CloudflareEvaluationError):
        return "OTHER_CLOUDFLARE_ERROR"
    candidate = str(error).split(" ", 1)[0]
    if candidate in _SAFE_CLOUDFLARE_ERROR_CODES:
        return candidate
    if re.fullmatch(r"HTTP_[1-5][0-9]{2}", candidate):
        return candidate
    if candidate.startswith("TRANSPORT_"):
        transport_type = candidate[len("TRANSPORT_"):]
        if transport_type in _SAFE_TRANSPORT_ERROR_TYPES:
            return candidate
    return "OTHER_CLOUDFLARE_ERROR"


def generate_evaluation_json(
    system_instructions,
    user_prompt,
    *,
    account_id=None,
    api_token=None,
    model=DEFAULT_MODEL,
    max_completion_tokens=1024,
    http_post=None,
    audit_metadata=None,
):
    """Return raw model JSON text to the existing evaluator for validation.

    Single attempt, bounded timeout, no retries. The caller owns the strict
    evaluation rubric. Account/token may be passed explicitly in unit tests.
    """
    if account_id is None:
        account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    if api_token is None:
        api_token = os.getenv("CLOUDFLARE_API_TOKEN", "")
    if not ACCOUNT_ID_PATTERN.fullmatch(account_id):
        raise CloudflareEvaluationError("MISSING_OR_INVALID_ACCOUNT_ID")
    if not api_token.strip():
        raise CloudflareEvaluationError("MISSING_API_TOKEN")
    if not isinstance(system_instructions, str) or not system_instructions.strip():
        raise CloudflareEvaluationError("INVALID_PROMPT")
    if not isinstance(user_prompt, str) or not user_prompt.strip():
        raise CloudflareEvaluationError("INVALID_PROMPT")
    if len(system_instructions) + len(user_prompt) > 28000:
        raise CloudflareEvaluationError("PROMPT_TOO_LONG")
    if model != DEFAULT_MODEL:
        raise CloudflareEvaluationError("UNAPPROVED_MODEL")
    if (
        isinstance(max_completion_tokens, bool)
        or not isinstance(max_completion_tokens, int)
        or not 256 <= max_completion_tokens <= 4096
    ):
        raise CloudflareEvaluationError("INVALID_COMPLETION_BUDGET")

    url = (
        f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1/"
        "chat/completions"
    )
    post = http_post or requests.post
    try:
        response = post(
            url,
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_instructions},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.1,
                "max_tokens": max_completion_tokens,
                "stream": False,
            },
            timeout=(5, 45),
        )
    except requests.RequestException as exc:
        raise CloudflareEvaluationError(
            f"TRANSPORT_{type(exc).__name__}"
        ) from None

    if response.status_code != 200:
        # Cloudflare 429 includes both temporary capacity and exhausted
        # daily Neurons; do not retry blindly or expose account details.
        raise CloudflareEvaluationError(f"HTTP_{response.status_code}")

    try:
        result = response.json()
        choice = result["choices"][0]
        message = choice["message"]
        content = message.get("content")
        usage = result.get("usage") or {}
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        raise CloudflareEvaluationError("INVALID_PROVIDER_RESPONSE") from None
    if not isinstance(message, dict) or not isinstance(usage, dict):
        raise CloudflareEvaluationError("INVALID_PROVIDER_RESPONSE")
    if audit_metadata is not None:
        if not isinstance(audit_metadata, dict):
            raise CloudflareEvaluationError("INVALID_AUDIT_METADATA")
        from .provider_audit_metrics import safe_completion_metadata
        audit_metadata.update(safe_completion_metadata(choice, usage))
    if not isinstance(content, str) or not content.strip():
        # Only report bounded, non-sensitive metadata: never the model's
        # reasoning text, raw response, credentials, or evidence input.
        finish = choice.get("finish_reason")
        if finish not in {"stop", "length", "tool_calls", "content_filter"}:
            finish = "other"
        completion_tokens = usage.get("completion_tokens")
        if (
            isinstance(completion_tokens, bool)
            or not isinstance(completion_tokens, int)
            or not 0 <= completion_tokens <= 1000000
        ):
            completion_tokens = "unknown"
        reasoning_present = bool(
            message.get("reasoning_content") or message.get("reasoning")
        )
        raise CloudflareEvaluationError(
            f"EMPTY_PROVIDER_RESPONSE finish_reason={finish} "
            f"completion_tokens={completion_tokens} "
            f"reasoning_present={str(reasoning_present).lower()}"
        )
    return content
