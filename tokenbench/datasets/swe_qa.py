"""SWE-QA dataset — free-form questions about pinned repos, judged by LLM.

Tasks are hand-curated against the same pinned snapshots used by
needle-codebase, so dataset_version 1.0.0 carries here unchanged. Questions
live in artifacts/swe_qa/v<dataset_version>/questions.jsonl as one
JSON-per-line record:

    {
      "task_id":  "swe-click-0000",       # globally unique
      "repo_id":  "click",                # must match a RepoPin.short_id
      "question": "...",                  # free-form question for the model
      "reference": "...",                 # gold reference text for the judge
      "difficulty": "easy|medium|hard",   # optional
      "meta": {...}                       # arbitrary diagnostic info
    }

Scoring is "llm_judge" — outputs are graded by tokenbench.judges.llm_judge,
not by string-contains. The reference is given to the judge as ground truth;
it is NEVER passed into the provider's context (DECISIONS.md #3, isolation).

The full dataset must contain >=200 tasks before SWE-QA results may be cited
in headline numbers (per CHUNK_05_judge.md and DECISIONS.md #11). The loader
itself does not enforce that floor — calibration scripts do.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from ..core.schemas import RepoRef, Task
from .base import Dataset
from .repo_pins import REPO_PINS

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
QUESTIONS_DIR = _PROJECT_ROOT / "artifacts" / "swe_qa"

CANARY_TEMPLATE = "TOKENBENCH-CANARY-swe-qa-{version}"


class SweQaDataset(Dataset):
    name = "swe-qa"
    dataset_version = "1.0.0"

    def __init__(
        self,
        *,
        version: str | None = None,
        questions_path: Path | None = None,
        repos: list = REPO_PINS,
    ):
        self.version = version or self.dataset_version
        self._pins_by_id = {p.short_id: p for p in repos}
        self.questions_path = questions_path or (
            QUESTIONS_DIR / f"v{self.version}" / "questions.jsonl"
        )

    def tasks(self) -> Iterator[Task]:
        if not self.questions_path.exists():
            raise FileNotFoundError(
                f"SWE-QA questions file missing: {self.questions_path}. "
                "Author it before loading."
            )
        canary = CANARY_TEMPLATE.format(version=self.version)
        with self.questions_path.open() as fh:
            for lineno, raw in enumerate(fh, start=1):
                raw = raw.strip()
                if not raw or raw.startswith("#"):
                    continue
                try:
                    rec = json.loads(raw)
                except json.JSONDecodeError as e:
                    raise ValueError(
                        f"{self.questions_path}:{lineno} invalid JSON: {e}"
                    ) from e
                yield self._record_to_task(rec, canary, lineno)

    def _record_to_task(self, rec: dict, canary: str, lineno: int) -> Task:
        for key in ("task_id", "repo_id", "question", "reference"):
            if key not in rec:
                raise ValueError(
                    f"{self.questions_path}:{lineno} missing required field: {key!r}"
                )
        repo_id = rec["repo_id"]
        if repo_id not in self._pins_by_id:
            raise ValueError(
                f"{self.questions_path}:{lineno} unknown repo_id={repo_id!r}; "
                f"expected one of {sorted(self._pins_by_id)}"
            )
        pin = self._pins_by_id[repo_id]
        meta = dict(rec.get("meta", {}))
        meta.setdefault("repo_id", repo_id)
        meta.setdefault("language", pin.language)
        if "difficulty" in rec:
            meta["difficulty"] = rec["difficulty"]
        return Task(
            task_id=rec["task_id"],
            dataset_version=self.version,
            task_type="repo_qa",
            question=rec["question"],
            repo=RepoRef(
                url=pin.url,
                commit=pin.commit,
                snapshot_sha256=pin.snapshot_sha256,
            ),
            gold=rec["reference"],
            needle=None,
            scoring="llm_judge",
            canary=canary,
            license=pin.license,
            meta=meta,
        )
