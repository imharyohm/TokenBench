"""Model adapter interface. Per DECISIONS.md #8 and §1[4].

The single chokepoint where token telemetry + traces are recorded.
Adding a new provider = new file conforming to this ABC.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelResponse:
    text: str
    native_input_tokens: int
    native_output_tokens: int
    norm_input_tokens: int   # re-counted in o200k_base
    norm_output_tokens: int  # re-counted in o200k_base
    latency_ms: int
    raw_trace: dict


class Model(ABC):
    """Provider-agnostic completion interface.

    Implementations live in tokenbench/models/<provider>.py.
    The runner only ever calls .complete() — it doesn't know which SDK is
    underneath.
    """

    name: str
    provider: str

    @abstractmethod
    def complete(self, prompt: str, *, max_tokens: int = 1024, seed: int = 0) -> ModelResponse: ...
