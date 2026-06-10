"""Execution engine — tasks × providers × models × repeats.

Chunk 4 upgrades:
  - **Seeded:** unchanged from Chunk 1 — every cell carries a seed.
  - **Idempotent:** before running a cell, the runner checks the store for
    a matching key `(task_id, provider_version, model, repeat, seed,
    dataset_version, harness_version)` and skips if present.
  - **Resumable:** because writes are immediate and idempotency is
    key-based, a kill mid-sweep + restart produces the same final store
    content as a clean run (modulo run_id and timestamp).
  - **Parallel:** opt-in via `RunConfig.concurrency`. Cells fan out across
    a `ThreadPoolExecutor`; the gateway latency dominates so threads are
    sufficient. concurrency=1 (default) preserves Chunk 3's exact wire
    behaviour.

Build artefacts (`provider.build(task)`) are memoised per `(provider,
task)` for the duration of one sweep so the same task isn't built once
per repeat.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Sequence

from .. import HARNESS_VERSION
from ..core.schemas import (
    ProviderRef,
    RunRecord,
    Score,
    Task,
    Telemetry,
)
from ..datasets.base import Dataset
from ..judges.base import Judge
from ..models.base import Model
from ..providers.base import BuildArtifact, Provider
from ..results.store import CellKey, ResultsStore, cell_key


@dataclass(frozen=True)
class RunConfig:
    repeats: int = 1
    base_seed: int = 0
    concurrency: int = 1  # 1 = sequential (Chunk 3 behaviour)


class _BuildCache:
    """Per-sweep memoisation of `(provider, task) -> BuildArtifact`.

    Build is the expensive one-time step; we don't re-run it across repeats
    of the same task. Thread-safe so parallel cells against the same
    (provider, task) wait on a single in-flight build.
    """

    def __init__(self):
        self._artifacts: dict[tuple[int, str], BuildArtifact] = {}
        self._locks: dict[tuple[int, str], threading.Lock] = {}
        self._meta_lock = threading.Lock()

    def get(self, provider: Provider, task: Task) -> BuildArtifact:
        key = (id(provider), task.task_id)
        with self._meta_lock:
            if key in self._artifacts:
                return self._artifacts[key]
            lock = self._locks.setdefault(key, threading.Lock())
        with lock:
            if key in self._artifacts:
                return self._artifacts[key]
            artifact = provider.build(task)
            self._artifacts[key] = artifact
            return artifact


class Runner:
    def __init__(self, store: ResultsStore):
        self.store = store

    def run_cell(
        self,
        task: Task,
        provider: Provider,
        model: Model,
        judge: Judge,
        repeat: int,
        seed: int,
        artifact: BuildArtifact | None = None,
    ) -> RunRecord:
        if artifact is None:
            artifact = provider.build(task)
        ctx = provider.retrieve(task, artifact)
        resp = model.complete(ctx.text, seed=seed)
        score: Score = judge.score(task, resp.text)

        telemetry = Telemetry(
            input_tokens_norm=ctx.input_tokens_norm,
            output_tokens_norm=resp.norm_output_tokens,
            cache_tokens_norm=0,
            build_tokens_norm=artifact.build_tokens_norm,
            native_input=resp.native_input_tokens,
            native_output=resp.native_output_tokens,
            latency_ms=resp.latency_ms,
            trace_uri=judge.trace_uri_for(task),
        )

        record = RunRecord(
            task_id=task.task_id,
            dataset_version=task.dataset_version,
            harness_version=HARNESS_VERSION,
            provider=ProviderRef(name=provider.name, version=provider.version, config=provider.config),
            model=model.name,
            repeat=repeat,
            seed=seed,
            telemetry=telemetry,
            score=score,
        )
        self.store.append(record)
        return record

    def sweep(
        self,
        dataset: Dataset,
        providers: Sequence[Provider],
        models: Sequence[Model],
        judge: Judge,
        config: RunConfig = RunConfig(),
        on_skip: Callable[[CellKey], None] | None = None,
    ) -> list[RunRecord]:
        tasks: list[Task] = list(dataset.tasks())
        dataset_version = tasks[0].dataset_version if tasks else None
        completed = self.store.completed_keys(
            dataset_version=dataset_version,
            harness_version=HARNESS_VERSION,
        )

        plan: list[tuple[Task, Provider, Model, int, int, CellKey]] = []
        for provider in providers:
            for model in models:
                for r in range(config.repeats):
                    for i, task in enumerate(tasks):
                        seed = config.base_seed + r * len(tasks) + i
                        key: CellKey = (
                            task.task_id,
                            provider.name,
                            provider.version,
                            model.name,
                            r,
                            seed,
                            task.dataset_version,
                            HARNESS_VERSION,
                        )
                        plan.append((task, provider, model, r, seed, key))

        build_cache = _BuildCache()

        def _execute(item) -> RunRecord | None:
            task, provider, model, repeat, seed, key = item
            if key in completed:
                if on_skip is not None:
                    on_skip(key)
                return None
            artifact = build_cache.get(provider, task)
            return self.run_cell(
                task, provider, model, judge,
                repeat=repeat, seed=seed, artifact=artifact,
            )

        out: list[RunRecord] = []
        if config.concurrency <= 1:
            for item in plan:
                rec = _execute(item)
                if rec is not None:
                    out.append(rec)
        else:
            with ThreadPoolExecutor(max_workers=config.concurrency) as pool:
                futures = [pool.submit(_execute, item) for item in plan]
                for fut in as_completed(futures):
                    rec = fut.result()
                    if rec is not None:
                        out.append(rec)
        return out


def cells_count(
    n_tasks: int, n_providers: int, n_models: int, repeats: int
) -> int:
    """Used by the cumulative cost ceiling (§3 P3): project before running."""
    return n_tasks * n_providers * n_models * repeats
