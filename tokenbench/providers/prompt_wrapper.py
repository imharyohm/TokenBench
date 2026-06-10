"""Standardized prompt wrapper used by every provider.

Per §2 of the architecture doc: prompt format is held constant across
providers so it isn't a confound. The single controlled variable between
providers is the CONTEXT they pack into this template — not the wording
around it.
"""

from __future__ import annotations

from typing import Final

SYSTEM_INSTRUCTION: Final = (
    "You answer questions about a codebase. "
    "Use only the provided context. "
    "When asked for a function name, reply with just the bare function name "
    "(no module path, no parentheses, no extra words)."
)

FREEFORM_SYSTEM_INSTRUCTION: Final = (
    "You are an expert Python engineer answering free-form questions about an "
    "open-source library. Use only the provided context. Be specific: name "
    "files, classes, and methods that appear in the context. Do not invent "
    "APIs or behavior not visible in the context. Aim for 3-7 sentences. "
    "If the context is insufficient, say so plainly."
)


def standard_prompt(*, context: str, question: str) -> str:
    return (
        f"{SYSTEM_INSTRUCTION}\n\n"
        f"<context>\n{context}\n</context>\n\n"
        f"Question: {question}\n"
        "Answer:"
    )


def freeform_prompt(*, context: str, question: str) -> str:
    """Free-form variant for SWE-QA tasks (task_type='repo_qa', scoring='llm_judge').

    Diverges from standard_prompt only in the system instruction; the
    <context>/Question:/Answer: structure is identical so context-token
    counts remain comparable across both prompt shapes.
    """
    return (
        f"{FREEFORM_SYSTEM_INSTRUCTION}\n\n"
        f"<context>\n{context}\n</context>\n\n"
        f"Question: {question}\n"
        "Answer:"
    )
