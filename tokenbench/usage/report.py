"""Roll up usage JSONL into per-day, per-model totals."""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Optional

from .tracker import UsageTracker, get_tracker


def totals_for_date(
    day: _dt.date,
    *,
    tracker: Optional[UsageTracker] = None,
) -> dict:
    """Return {'by_model': {model: {...}}, 'totals': {...}, 'calls': int}."""
    tracker = tracker or get_tracker()
    path = tracker.log_dir / f"{day.isoformat()}.jsonl"
    by_model: dict[str, dict[str, int]] = {}
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read": 0,
        "cache_creation": 0,
        "total_tokens": 0,
    }
    calls = 0
    if not path.exists():
        return {"date": day.isoformat(), "calls": 0, "by_model": {}, "totals": totals, "path": str(path)}

    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            calls += 1
            m = row.get("model", "unknown")
            slot = by_model.setdefault(
                m,
                {"calls": 0, "input_tokens": 0, "output_tokens": 0,
                 "cache_read": 0, "cache_creation": 0, "total_tokens": 0},
            )
            slot["calls"] += 1
            for k in ("input_tokens", "output_tokens", "cache_read",
                      "cache_creation", "total_tokens"):
                slot[k] += int(row.get(k, 0) or 0)
                totals[k] += int(row.get(k, 0) or 0)

    return {
        "date": day.isoformat(),
        "calls": calls,
        "by_model": by_model,
        "totals": totals,
        "path": str(path),
    }


def today_totals(*, tracker: Optional[UsageTracker] = None) -> dict:
    today = _dt.datetime.now(_dt.timezone.utc).date()
    return totals_for_date(today, tracker=tracker)


def format_report(report: dict) -> str:
    lines = []
    lines.append(f"Usage on {report['date']}  ({report['calls']} calls)")
    lines.append(f"  log: {report['path']}")
    if not report["by_model"]:
        lines.append("  (no calls recorded)")
        return "\n".join(lines)

    width = max(len(m) for m in report["by_model"]) + 2
    header = f"  {'model'.ljust(width)} {'calls':>6}  {'in':>10}  {'out':>10}  {'cache_r':>10}  {'cache_w':>10}  {'total':>10}"
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))
    for m, s in sorted(report["by_model"].items()):
        lines.append(
            f"  {m.ljust(width)} {s['calls']:>6}  "
            f"{s['input_tokens']:>10}  {s['output_tokens']:>10}  "
            f"{s['cache_read']:>10}  {s['cache_creation']:>10}  "
            f"{s['total_tokens']:>10}"
        )
    t = report["totals"]
    lines.append("  " + "-" * (len(header) - 2))
    lines.append(
        f"  {'TOTAL'.ljust(width)} {report['calls']:>6}  "
        f"{t['input_tokens']:>10}  {t['output_tokens']:>10}  "
        f"{t['cache_read']:>10}  {t['cache_creation']:>10}  "
        f"{t['total_tokens']:>10}"
    )
    return "\n".join(lines)


def main():  # python -m tokenbench.usage.report [YYYY-MM-DD]
    import sys
    if len(sys.argv) > 1:
        day = _dt.date.fromisoformat(sys.argv[1])
        report = totals_for_date(day)
    else:
        report = today_totals()
    print(format_report(report))


if __name__ == "__main__":
    main()
