"""Batch report generation progress persistence (resume from last completed client)."""
import json
import os
from datetime import date, datetime
from typing import Any, Dict, List, Optional


def _default_progress_path() -> str:
    """Path to the progress file (project root)."""
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "batch_progress.json")


def load_batch_progress(path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Load batch progress from file. Returns None if file missing or invalid."""
    path = path or _default_progress_path()
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        if "period_start" not in data or "period_end" not in data or "completed_clients" not in data:
            return None
        return data
    except (json.JSONDecodeError, OSError):
        return None


def save_batch_progress(
    path: Optional[str],
    period_start: date,
    period_end: date,
    total_count: int,
    completed_clients: List[str],
    last_completed: Optional[str],
) -> None:
    """Persist batch progress to file."""
    path = path or _default_progress_path()
    data = {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "total_count": total_count,
        "completed_clients": list(completed_clients),
        "last_completed": last_completed,
        "updated_at": datetime.now().isoformat(),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clear_batch_progress(path: Optional[str] = None) -> None:
    """Remove progress file (e.g. when batch is fully complete)."""
    path = path or _default_progress_path()
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass


def progress_matches_period(progress: Dict[str, Any], start_date: date, end_date: date) -> bool:
    """Return True if saved progress is for the same period."""
    try:
        start = progress.get("period_start")
        end = progress.get("period_end")
        if not start or not end:
            return False
        return (
            datetime.fromisoformat(start).date() == start_date
            and datetime.fromisoformat(end).date() == end_date
        )
    except (ValueError, TypeError):
        return False
