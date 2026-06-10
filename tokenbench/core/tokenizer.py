"""Reference-tokenizer normalization. Locked to o200k_base per DECISIONS.md #1.

Every *_norm field in the Telemetry schema must be counted with this encoder.
"""

from __future__ import annotations

from functools import lru_cache

import tiktoken

REFERENCE_ENCODING = "o200k_base"


@lru_cache(maxsize=1)
def _encoder():
    return tiktoken.get_encoding(REFERENCE_ENCODING)


def count_tokens(text: str) -> int:
    """Token count under the reference tokenizer.

    Empty string returns 0 (tiktoken would too, but explicit guard avoids the
    encode call on the hot path).
    """
    if not text:
        return 0
    return len(_encoder().encode(text))
