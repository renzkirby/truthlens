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


def generate_evaluation_json(
    system_instructions,
    user_prompt,
    *,
    account_id=None,
    api_token=None,
    model=DEFAULT_MODEL,
    http_post=None,
):
    """Return raw model JSON text to the existing evaluator for validation.

    Single attempt, bounded timeout, no retries. The caller owns the strict
    evaluation rubric. Account/token may be passed explicitly in unit tests.
    """
    account_id = account_id or os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    api_token = api_token or os.getenv("CLOUDFLARE_API_TOKEN", "")
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
                "max_tokens": 1024,
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
        content = response.json()["choices"][0]["message"]["content"]
    except (ValueError, TypeError, KeyError, IndexError):
        raise CloudflareEvaluationError("INVALID_PROVIDER_RESPONSE") from None
    if not isinstance(content, str) or not content.strip():
        raise CloudflareEvaluationError("EMPTY_PROVIDER_RESPONSE")
    return content
