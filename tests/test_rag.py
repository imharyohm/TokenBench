import pytest

from tokenbench.core.tokenizer import count_tokens
from tokenbench.providers.rag import (
    BM25RagProvider,
    FROZEN_CONFIG,
    _chunk_file,
    _tokenize,
)
from tokenbench.providers.prompt_wrapper import standard_prompt


def test_chunker_covers_all_tokens():
    text = " ".join(f"word{i}" for i in range(500))
    chunks = list(_chunk_file(text, chunk_tokens=100, overlap=20))
    assert len(chunks) > 1
    # union of chunks must contain (almost) the full text
    assert "word0" in chunks[0]
    assert "word499" in chunks[-1]


def test_tokenize_handles_camelcase_and_snake():
    toks = _tokenize("HelloWorld snake_case_thing 1234")
    # camelCase splits weakly via regex; snake_case is one identifier
    assert "snake_case_thing" in toks
    assert "1234" in toks


def test_frozen_config_is_locked_dict():
    assert FROZEN_CONFIG["top_k"] == 5
    assert FROZEN_CONFIG["chunk_tokens"] == 200
    # provider exposes a copy of FROZEN_CONFIG (not a reference) so a caller
    # mutating .config doesn't change the global frozen knobs
    p = BM25RagProvider()
    p.config["top_k"] = 99
    assert FROZEN_CONFIG["top_k"] == 5


def test_standard_prompt_shape():
    p = standard_prompt(context="abc", question="what?")
    assert "<context>" in p and "</context>" in p
    assert p.endswith("Answer:")
    assert count_tokens(p) > 0
