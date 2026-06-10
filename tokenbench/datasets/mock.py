"""Synthetic dataset for Chunk 1. Auto-contains scoring against a known gold."""

from __future__ import annotations

from typing import Iterator

from ..core.schemas import RepoRef, Task
from .base import Dataset


class MockDataset(Dataset):
    def __init__(self, *, n_tasks: int = 20, dataset_version: str = "1.0.0-mock"):
        self.name = "mock"
        self.dataset_version = dataset_version
        self.n_tasks = n_tasks

    def tasks(self) -> Iterator[Task]:
        for i in range(self.n_tasks):
            yield Task(
                task_id=f"mock-{i:04d}",
                dataset_version=self.dataset_version,
                task_type="needle_function",
                question=f"Which function handles request type {i}?",
                repo=RepoRef(url="mock://repo", commit=f"mock{i:04d}"),
                gold=f"handle_request_{i}",
                needle=f"handle_request_{i}",
                scoring="auto_contains",
                canary="TOKENBENCH-CANARY-mock-1.0.0",
                license="CC0",
                meta={"language": "python", "synthetic": True},
            )
