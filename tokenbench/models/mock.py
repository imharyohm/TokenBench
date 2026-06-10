"""Deterministic mock model for Chunk 1. No network, seeded.

Returns the gold answer with a tunable correctness rate and a tunable
output-token budget. Used by run_demo.py to exercise the full pipeline.
"""

from __future__ import annotations

import hashlib
import random

from ..core.tokenizer import count_tokens
from .base import Model, ModelResponse


class MockModel(Model):
    def __init__(
        self,
        name: str = "mock-1",
        *,
        correctness_rate: float = 1.0,
        output_token_budget: int = 16,
        latency_ms: int = 5,
    ):
        self.name = name
        self.provider = "mock"
        self.correctness_rate = correctness_rate
        self.output_token_budget = output_token_budget
        self.latency_ms = latency_ms

    def complete(self, prompt: str, *, max_tokens: int = 1024, seed: int = 0) -> ModelResponse:
        # Deterministic: same (prompt, seed) -> same response.
        h = hashlib.sha256(f"{seed}|{prompt}".encode()).digest()
        rng = random.Random(int.from_bytes(h[:8], "big"))
        is_correct = rng.random() < self.correctness_rate

        # Mock pretends the prompt's last "GOLD:..." line is the gold answer
        # and either echoes it (correct) or returns a stub (incorrect).
        gold = _extract_gold(prompt)
        text = gold if (is_correct and gold) else "i_dont_know"

        # Truncate to output_token_budget (rough, by char proxy — fine for mock).
        text = text[: self.output_token_budget * 4]

        norm_in = count_tokens(prompt)
        norm_out = count_tokens(text)

        return ModelResponse(
            text=text,
            native_input_tokens=norm_in,    # mock: native == norm
            native_output_tokens=norm_out,
            norm_input_tokens=norm_in,
            norm_output_tokens=norm_out,
            latency_ms=self.latency_ms,
            raw_trace={"prompt": prompt, "response": text, "seed": seed},
        )


def _extract_gold(prompt: str) -> str:
    """The Mock provider/scoring contract uses a 'GOLD: <answer>' marker so
    the mock can pretend to know the answer some fraction of the time."""
    for line in prompt.splitlines():
        if line.startswith("GOLD:"):
            return line[len("GOLD:") :].strip()
    return ""
