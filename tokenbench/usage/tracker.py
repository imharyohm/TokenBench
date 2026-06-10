"""Local token-usage tracker.

The upstream gateway exposes inference + key identity but blocks every
admin/spend route ("fault filter abort"), so we cannot ask the proxy how
many tokens this key has burned today. We can, however, record exactly
what we send and receive.

Every Anthropic API call writes one line to artifacts/usage/YYYY-MM-DD.jsonl
with the native usage block from the response. report.py rolls those up.

JSONL schema:
    {
      "ts":              ISO-8601 UTC,
      "model":           full model id,
      "input_tokens":    int (native),
      "output_tokens":   int (native),
      "cache_read":      int (cache_read_input_tokens, may be 0),
      "cache_creation":  int (cache_creation_input_tokens, may be 0),
      "total_tokens":    int,
      "latency_ms":      int,
      "response_id":     str | null,
    }
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import threading
from pathlib import Path
from typing import Optional


def _default_log_dir() -> Path:
    """Pick a writable usage-log directory.

    Honours TOKENBENCH_USAGE_DIR if set; otherwise writes alongside the
    project's existing artifacts/ directory when one is present, falling
    back to ~/.tokenbench/usage.
    """
    override = os.environ.get("TOKENBENCH_USAGE_DIR")
    if override:
        return Path(override).expanduser().resolve()

    cwd = Path.cwd()
    if (cwd / "artifacts").is_dir():
        return (cwd / "artifacts" / "usage").resolve()

    pkg_root = Path(__file__).resolve().parent.parent.parent
    if (pkg_root / "artifacts").is_dir():
        return (pkg_root / "artifacts" / "usage").resolve()

    return (Path.home() / ".tokenbench" / "usage").resolve()


class UsageTracker:
    """Append-only daily-rotated JSONL writer. Thread-safe."""

    def __init__(self, log_dir: Optional[Path] = None):
        self.log_dir = Path(log_dir) if log_dir is not None else _default_log_dir()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path_for(self, day: _dt.date) -> Path:
        return self.log_dir / f"{day.isoformat()}.jsonl"

    def log(
        self,
        *,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read: int = 0,
        cache_creation: int = 0,
        latency_ms: int = 0,
        response_id: Optional[str] = None,
        ts: Optional[_dt.datetime] = None,
    ) -> None:
        ts = ts or _dt.datetime.now(_dt.timezone.utc)
        record = {
            "ts": ts.isoformat(),
            "model": model,
            "input_tokens": int(input_tokens),
            "output_tokens": int(output_tokens),
            "cache_read": int(cache_read),
            "cache_creation": int(cache_creation),
            "total_tokens": int(input_tokens) + int(output_tokens),
            "latency_ms": int(latency_ms),
            "response_id": response_id,
        }
        line = json.dumps(record, ensure_ascii=False) + "\n"
        path = self._path_for(ts.date())
        with self._lock:
            with path.open("a") as f:
                f.write(line)


_tracker: Optional[UsageTracker] = None
_tracker_lock = threading.Lock()


def get_tracker() -> UsageTracker:
    """Process-wide singleton. First call decides the log directory."""
    global _tracker
    if _tracker is None:
        with _tracker_lock:
            if _tracker is None:
                _tracker = UsageTracker()
    return _tracker


def log_call(**kwargs) -> None:
    """Convenience wrapper around get_tracker().log()."""
    get_tracker().log(**kwargs)
