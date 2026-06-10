import os

import pytest

from tokenbench.core.env import load_env

load_env()

pytestmark = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_AUTH_TOKEN") and not os.getenv("ANTHROPIC_API_KEY"),
    reason="no ANTHROPIC credentials in env; skipping live adapter test",
)


def test_adapter_returns_normalized_and_native_tokens():
    from tokenbench.models.anthropic import AnthropicModel

    m = AnthropicModel("bedrock.anthropic.claude-sonnet-4-5")
    r = m.complete("Reply with exactly the word: pong", max_tokens=8)
    assert "pong" in r.text.lower()
    # native and norm both populated
    assert r.native_input_tokens > 0
    assert r.native_output_tokens > 0
    assert r.norm_input_tokens > 0
    assert r.norm_output_tokens > 0
    # latency captured
    assert r.latency_ms > 0
    # trace captured
    assert "request" in r.raw_trace
    assert "usage" in r.raw_trace
