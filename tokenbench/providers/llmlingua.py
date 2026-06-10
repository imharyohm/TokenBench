"""LLMLingua-2 provider — composes a prompt compressor on top of BM25 RAG.

LLMLingua-2 (Pan et al. 2024) is a small classifier that drops tokens from a
prompt while preserving meaning. It composes ON TOP of another retrieval
method — here we put it on BM25 RAG (which already produces ~1k context).

Frozen config (DECISIONS.md #6):
- model: microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank
  (the small CPU-friendly LLMLingua-2 model, not the Llama-2-7b default)
- target_ratio: 0.5  (retain ~50% of tokens — the paper's headline number)
- base provider: BM25RagProvider with its own frozen config

Build cost = 0 (the compressor model is loaded locally, not via the gateway;
no LLM call is made during build). Per-query cost = compressed input length.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from ..core.schemas import Task
from ..core.tokenizer import count_tokens
from .base import BuildArtifact, Provider, RetrievedContext
from .prompt_wrapper import standard_prompt
from .rag import BM25RagProvider, _BM25Payload, _tokenize, FROZEN_CONFIG as RAG_FROZEN

# Silence transformers progress bars; CPU-only.
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

FROZEN_CONFIG = {
    "compressor_model": "microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank",
    "use_llmlingua2": True,
    "target_ratio": 0.5,
    "device_map": "cpu",
    "base_provider": "rag-bm25",
    "base_config": dict(RAG_FROZEN),
}


@dataclass(frozen=True)
class _LLMLinguaPayload:
    repo_id: str
    base_payload: _BM25Payload  # the BM25 index from the inner provider


class LLMLinguaProvider(Provider):
    """LLMLingua-2 prompt compression composed on BM25 RAG."""

    name = "llmlingua-rag"
    version = "0.1.0"
    config = dict(FROZEN_CONFIG)

    def __init__(self):
        self._base = BM25RagProvider()
        self._compressor = None  # lazy: first retrieve() loads the model

    def _load_compressor(self):
        if self._compressor is None:
            from llmlingua import PromptCompressor
            self._compressor = PromptCompressor(
                model_name=FROZEN_CONFIG["compressor_model"],
                use_llmlingua2=FROZEN_CONFIG["use_llmlingua2"],
                device_map=FROZEN_CONFIG["device_map"],
            )
        return self._compressor

    def build(self, task: Task) -> BuildArtifact:
        # Inner BM25 build is reused; build cost is the BM25 build cost
        # (compressor is local, no gateway tokens).
        inner = self._base.build(task)
        return BuildArtifact(
            payload=_LLMLinguaPayload(
                repo_id=task.meta["repo_id"],
                base_payload=inner.payload,  # type: ignore[arg-type]
            ),
            build_tokens_norm=inner.build_tokens_norm,
        )

    def retrieve(self, task: Task, artifact: BuildArtifact) -> RetrievedContext:
        payload: _LLMLinguaPayload = artifact.payload  # type: ignore[assignment]
        # Reproduce BM25 retrieval (same scoring, same top_k).
        scores = payload.base_payload.bm25.get_scores(_tokenize(task.question))
        top_k = RAG_FROZEN["top_k"]
        order = sorted(range(len(scores)), key=lambda i: -scores[i])[:top_k]
        retrieved = [payload.base_payload.chunks[i] for i in order]
        raw_context = "\n\n".join(f"# file: {c.file}\n{c.text}" for c in retrieved)

        compressor = self._load_compressor()
        result = compressor.compress_prompt(
            raw_context,
            rate=FROZEN_CONFIG["target_ratio"],
            force_tokens=["\n", "?", "!", "."],
        )
        compressed = result["compressed_prompt"]

        prompt = standard_prompt(context=compressed, question=task.question)
        return RetrievedContext(text=prompt, input_tokens_norm=count_tokens(prompt))
