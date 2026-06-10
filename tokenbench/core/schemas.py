"""Frozen Task and RunRecord schemas. Per §4 of tokenbench_architecture.md.

These are the contract between every component. Changing them requires a
new dataset_version or harness_version and invalidates prior comparisons.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

TaskType = Literal["needle_function", "repo_qa", "patch"]
ScoringKind = Literal["auto_contains", "unit_test", "llm_judge"]


class RepoRef(BaseModel):
    """Pinned repository pointer. Content-addressed via snapshot_sha256."""

    model_config = ConfigDict(frozen=True)

    url: str
    commit: str
    snapshot_sha256: Optional[str] = None
    docker_image: Optional[str] = None


class Task(BaseModel):
    """A versioned, machine-readable task record. §4 task schema."""

    model_config = ConfigDict(frozen=True)

    task_id: str
    dataset_version: str
    task_type: TaskType
    question: str
    repo: RepoRef
    gold: str
    needle: Optional[str] = None
    scoring: ScoringKind
    canary: str
    license: str
    meta: dict = Field(default_factory=dict)


class ProviderRef(BaseModel):
    """The single controlled variable in a run."""

    model_config = ConfigDict(frozen=True)

    name: str
    version: str
    config: dict = Field(default_factory=dict)


class Telemetry(BaseModel):
    """Per-attempt usage. Native vs normalized are both required."""

    model_config = ConfigDict(frozen=True)

    input_tokens_norm: int
    output_tokens_norm: int
    cache_tokens_norm: int = 0
    build_tokens_norm: int = 0

    native_input: int = 0
    native_output: int = 0

    latency_ms: int = 0
    trace_uri: Optional[str] = None


class Score(BaseModel):
    model_config = ConfigDict(frozen=True)

    correct: bool
    raw: float
    scorer: ScoringKind


class RunRecord(BaseModel):
    """Immutable, append-only run record. One per cell. §4 run-record schema."""

    model_config = ConfigDict(frozen=True)

    run_id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str
    dataset_version: str
    harness_version: str
    provider: ProviderRef
    model: str
    repeat: int
    seed: int
    telemetry: Telemetry
    score: Score
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
