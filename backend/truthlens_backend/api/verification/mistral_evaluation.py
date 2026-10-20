"""Development-only Mistral Small 4 adapter for comparison, never live routing."""
import os

import requests

from .provider_audit_metrics import safe_completion_metadata


DEFAULT_MISTRAL_MODEL = "mistral-small-2603"


class MistralEvaluationError(RuntimeError):
    """Sanitized model-transport failure; never contains provider response text."""


def generate_mistral_evaluation_json(
    system_instructions,
    user_prompt,
    *,
    api_token=None,
    model=DEFAULT_MISTRAL_MODEL,
    max_completion_tokens=2048,
    http_post=None,
    audit_metadata=None,
):
    if api_token is None:
        api_token = os.getenv("MISTRAL_API_KEY", "")
    if not isinstance(api_token, str) or not api_token.strip():
        raise MistralEvaluationError("MISSING_API_TOKEN")
    if model != DEFAULT_MISTRAL_MODEL:
        raise MistralEvaluationError("UNAPPROVED_MODEL")
    if (
        isinstance(max_completion_tokens, bool)
        or type(max_completion_tokens) is not int
        or not 256 <= max_completion_tokens <= 4096
    ):
        raise MistralEvaluationError("INVALID_COMPLETION_BUDGET")
    if not all(isinstance(p, str) and p.strip()
               for p in (system_instructions, user_prompt)):
        raise MistralEvaluationError("INVALID_PROMPT")
    if len(system_instructions) + len(user_prompt) > 28000:
        raise MistralEvaluationError("PROMPT_TOO_LONG")
    if audit_metadata is not None and not isinstance(audit_metadata, dict):
        raise MistralEvaluationError("INVALID_AUDIT_METADATA")

    post = http_post or requests.post
    try:
        response = post(
            "https://api.mistral.ai/v1/chat/completions",
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
        raise MistralEvaluationError(
            f"TRANSPORT_{type(exc).__name__}"
        ) from None
    if response.status_code != 200:
        raise MistralEvaluationError(f"HTTP_{response.status_code}")
    try:
        data = response.json()
        choice = data["choices"][0]
        message = choice["message"]
        content = message.get("content")
        usage = data.get("usage") or {}
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        raise MistralEvaluationError("INVALID_PROVIDER_RESPONSE") from None
    if not isinstance(message, dict) or not isinstance(usage, dict):
        raise MistralEvaluationError("INVALID_PROVIDER_RESPONSE")
    if audit_metadata is not None:
        audit_metadata.update(safe_completion_metadata(choice, usage))
    if not isinstance(content, str) or not content.strip():
        raise MistralEvaluationError("EMPTY_PROVIDER_RESPONSE")
    return content
