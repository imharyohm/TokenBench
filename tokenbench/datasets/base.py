"""Dataset interface — yields Tasks. Frozen by dataset_version."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator

from ..core.schemas import Task


class Dataset(ABC):
    name: str
    dataset_version: str

    @abstractmethod
    def tasks(self) -> Iterator[Task]: ...

    def __iter__(self) -> Iterator[Task]:
        return self.tasks()
