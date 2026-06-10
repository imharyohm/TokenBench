import pytest
from pydantic import ValidationError

from tokenbench.core.schemas import (
    ProviderRef,
    RepoRef,
    RunRecord,
    Score,
    Task,
    Telemetry,
)


def make_task() -> Task:
    return Task(
        task_id="repoqa-py-django-0007",
        dataset_version="1.0.0",
        task_type="needle_function",
        question="Which function validates the session token?",
        repo=RepoRef(
            url="https://github.com/example/django",
            commit="a1b2c3d4e5f6",
            snapshot_sha256="deadbeef" * 8,
        ),
        gold="validate_session_token",
        needle="validate_session_token",
        scoring="auto_contains",
        canary="TOKENBENCH-CANARY-uuid",
        license="BSD-3-Clause",
        meta={"language": "python", "repo_loc": 312000},
    )


def test_task_constructs():
    t = make_task()
    assert t.task_id == "repoqa-py-django-0007"
    assert t.scoring == "auto_contains"


def test_task_is_frozen():
    t = make_task()
    with pytest.raises(ValidationError):
        t.task_id = "different"


def test_task_type_must_be_known():
    with pytest.raises(ValidationError):
        Task(
            task_id="x",
            dataset_version="1.0.0",
            task_type="garbage",  # type: ignore[arg-type]
            question="?",
            repo=RepoRef(url="u", commit="c"),
            gold="g",
            scoring="auto_contains",
            canary="c",
            license="l",
        )


def test_run_record_defaults():
    r = RunRecord(
        task_id="repoqa-0001",
        dataset_version="1.0.0",
        harness_version="0.1.0",
        provider=ProviderRef(name="mock", version="0.0.1"),
        model="mock-1",
        repeat=0,
        seed=42,
        telemetry=Telemetry(input_tokens_norm=100, output_tokens_norm=10),
        score=Score(correct=True, raw=1.0, scorer="auto_contains"),
    )
    assert r.run_id  # auto-generated uuid
    assert r.timestamp is not None
    assert r.telemetry.cache_tokens_norm == 0
    assert r.telemetry.build_tokens_norm == 0


def test_run_record_is_frozen():
    r = RunRecord(
        task_id="t",
        dataset_version="1.0.0",
        harness_version="0.1.0",
        provider=ProviderRef(name="mock", version="0.0.1"),
        model="mock-1",
        repeat=0,
        seed=0,
        telemetry=Telemetry(input_tokens_norm=1, output_tokens_norm=1),
        score=Score(correct=False, raw=0.0, scorer="auto_contains"),
    )
    with pytest.raises(ValidationError):
        r.repeat = 5
