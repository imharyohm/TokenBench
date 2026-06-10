"""Anthropic model adapter — first real Model implementation.

Per DECISIONS.md #8: this adapter is the chokepoint where token telemetry
+ trace are recorded. Native tokens come from the SDK's usage API
(ground truth, matches billing). Normalized tokens are re-counted in
o200k_base for fair cross-model comparison.

The adapter respects the standard Anthropic env vars:
- ANTHROPIC_BASE_URL  — overridable to a gateway
- ANTHROPIC_AUTH_TOKEN — bearer token (used as Authorization: Bearer ...)
- ANTHROPIC_API_KEY    — alternative; x-api-key style auth
"""

from __future__ import annotations

import os
import time
from typing import Optional

import anthropic

from ..core.env import load_env
from ..core.tokenizer import count_tokens
from ..usage import log_call
from .base import Model, ModelResponse


class AnthropicModel(Model):
    def __init__(
        self,
        model_name: str,
        *,
        base_url: Optional[str] = None,
        auth_token: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_s: float = 60.0,
    ):
        load_env()
        self.name = model_name
        self.provider = "anthropic"

        # Build client. SDK reads ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN /
        # ANTHROPIC_API_KEY from env automatically; explicit args override.
        kwargs: dict = {"timeout": timeout_s}
        if base_url is not None:
            kwargs["base_url"] = base_url
        elif os.getenv("ANTHROPIC_BASE_URL"):
            kwargs["base_url"] = os.environ["ANTHROPIC_BASE_URL"]

        if auth_token is not None:
            kwargs["auth_token"] = auth_token
        elif os.getenv("ANTHROPIC_AUTH_TOKEN"):
            kwargs["auth_token"] = os.environ["ANTHROPIC_AUTH_TOKEN"]
        elif api_key is not None:
            kwargs["api_key"] = api_key

        self.client = anthropic.Anthropic(**kwargs)

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 1024,
        seed: int = 0,
    ) -> ModelResponse:
        # Anthropic API has no `seed` parameter; the seed is captured into the
        # trace for reproducibility bookkeeping but the call itself is
        # nondeterministic. The runner records the seed independently.
        # Gateway routes OpenAI-prefixed models to the OpenAI API, which
        # requires max_output_tokens >= 16.
        effective_max = max(max_tokens, 16) if self.name.startswith("openai.") else max_tokens
        t0 = time.time()
        resp = self.client.messages.create(
            model=self.name,
            max_tokens=effective_max,
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = int((time.time() - t0) * 1000)

        text = "".join(
            block.text for block in resp.content if getattr(block, "type", None) == "text"
        )

        cache_read = int(getattr(resp.usage, "cache_read_input_tokens", 0) or 0)
        cache_creation = int(getattr(resp.usage, "cache_creation_input_tokens", 0) or 0)
        try:
            log_call(
                model=self.name,
                input_tokens=resp.usage.input_tokens,
                output_tokens=resp.usage.output_tokens,
                cache_read=cache_read,
                cache_creation=cache_creation,
                latency_ms=latency_ms,
                response_id=getattr(resp, "id", None),
            )
        except Exception:
            # Telemetry must never break a benchmark run.
            pass

        return ModelResponse(
            text=text,
            native_input_tokens=resp.usage.input_tokens,
            native_output_tokens=resp.usage.output_tokens,
            norm_input_tokens=count_tokens(prompt),
            norm_output_tokens=count_tokens(text),
            latency_ms=latency_ms,
            raw_trace={
                "request": {"model": self.name, "prompt": prompt, "seed": seed},
                "response_id": resp.id,
                "stop_reason": resp.stop_reason,
                "usage": {
                    "input_tokens": resp.usage.input_tokens,
                    "output_tokens": resp.usage.output_tokens,
                    "cache_read_input_tokens": cache_read,
                    "cache_creation_input_tokens": cache_creation,
                },
                "text": text,
            },
        )
