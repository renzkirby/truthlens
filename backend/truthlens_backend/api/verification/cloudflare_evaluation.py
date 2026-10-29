"""Opt-in, development-only Cloudflare Workers AI model evaluation.

Not imported by the live factual-verification provider router. Never logs
prompts, evidence, responses, credentials or vendor error bodies.
"""
import os
import re

import requests


DEFAULT_MODEL = "@cf/google/gemma-4-26b-a4b-it"
MAX_INPUT_CHARS = 28000
DEFAULT_HTTP_TIMEOUT = (5, 45)
ACCOUNT_ID_PATTERN = re.compile(r"^[a-fA-F0-9]{32}$")


class CloudflareEvaluationError(RuntimeError):
    """Sanitized provider failure from the bounded Cloudflare adapter."""


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
    "INVALID_ASSESSMENT_INPUT",
    "INVALID_ASSESSMENT_JSON",
    "INVALID_CLASSIFICATION_INPUT",
    "INVALID_CLASSIFICATION_JSON",
    "ASSESSMENT_BATCH_TOO_LARGE",
    "INVALID_HTTP_TIMEOUT",
    "INVALID_REJECT_IF_BUSY",
    "HTTP_429_CAPACITY",
    "HTTP_429_ALLOCATION",
    "INVALID_PILOT_OPERATION",
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
    http_timeout=None,
    reject_if_busy=False,
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
    if len(system_instructions) + len(user_prompt) > MAX_INPUT_CHARS:
        raise CloudflareEvaluationError("PROMPT_TOO_LONG")
    if model != DEFAULT_MODEL:
        raise CloudflareEvaluationError("UNAPPROVED_MODEL")
    if (
        isinstance(max_completion_tokens, bool)
        or not isinstance(max_completion_tokens, int)
        or not 256 <= max_completion_tokens <= 4096
    ):
        raise CloudflareEvaluationError("INVALID_COMPLETION_BUDGET")
    if http_timeout is None:
        http_timeout = DEFAULT_HTTP_TIMEOUT
    elif (
        not isinstance(http_timeout, tuple)
        or len(http_timeout) != 2
        or any(type(part) is not int for part in http_timeout)
        or not (1 <= http_timeout[0] <= 5)
        or not (1 <= http_timeout[1] <= 45)
    ):
        raise CloudflareEvaluationError("INVALID_HTTP_TIMEOUT")
    if type(reject_if_busy) is not bool:
        raise CloudflareEvaluationError("INVALID_REJECT_IF_BUSY")

    url = (
        f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1/"
        "chat/completions"
    )
    post = http_post or requests.post
    request_body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_instructions},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
        "max_tokens": max_completion_tokens,
        "stream": False,
    }
    if reject_if_busy:
        # Cloudflare's OpenAI-compatible /ai/v1/chat/completions supports
        # options.rejectIfBusy. Only explicitly opted-in assessment or classification requests add it.
        request_body["options"] = {"rejectIfBusy": True}
    try:
        response = post(
            url,
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            },
            json=request_body,
            timeout=http_timeout,
        )
    except requests.RequestException as exc:
        raise CloudflareEvaluationError(
            f"TRANSPORT_{type(exc).__name__}"
        ) from None

    if response.status_code != 200:
        # Distinguish two documented Cloudflare 429 subcodes *only* when
        # returned as trusted numeric fields. Never log vendor messages,
        # request data or arbitrary HTTP response content.
        safe_code = f"HTTP_{response.status_code}"
        if response.status_code == 429:
            try:
                body = response.json()
            except (ValueError, TypeError, AttributeError):
                body = None
            if isinstance(body, dict):
                candidates = []
                error = body.get("error")
                if isinstance(error, dict):
                    candidates.append(error.get("code"))
                errors = body.get("errors")
                if isinstance(errors, list):
                    for item in errors[:4]:
                        if isinstance(item, dict):
                            candidates.append(item.get("code"))
                if 3040 in candidates:
                    safe_code = "HTTP_429_CAPACITY"
                elif 3036 in candidates:
                    safe_code = "HTTP_429_ALLOCATION"
        raise CloudflareEvaluationError(safe_code)

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
