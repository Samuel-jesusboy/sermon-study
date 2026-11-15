"""Records the tokens and cost of every AI call made while processing a sermon or answering a request.

Usage:
    with usage.tracking(db, user_id, job_id=...) as t:
        ... any ai.* calls ...
        t.sermon_id = new_sermon_id
    # rows are written to ai_usage when the block ends; t.total_cost has the sum
"""
import contextvars
import logging
from contextlib import contextmanager
from typing import Optional

from . import pricing

log = logging.getLogger("usage")
_current: contextvars.ContextVar[Optional["Tracker"]] = contextvars.ContextVar("usage_tracker", default=None)


class Tracker:
    def __init__(self, db, user_id: str, sermon_id: Optional[str] = None, job_id: Optional[str] = None):
        self.db, self.user_id, self.sermon_id, self.job_id = db, user_id, sermon_id, job_id
        self.records: list[dict] = []

    @property
    def total_cost(self) -> float:
        return round(sum(r["cost_usd"] or 0 for r in self.records), 6)

    @property
    def models_used(self) -> dict:
        out: dict[str, str] = {}
        for r in self.records:
            out.setdefault(r["task"], r["model"])
        return out

    def flush(self) -> None:
        if not self.records or self.db is None:
            return
        rows = [{**r, "user_id": self.user_id, "sermon_id": self.sermon_id, "job_id": self.job_id}
                for r in self.records]
        try:
            self.db.table("ai_usage").insert(rows).execute()
        except Exception as e:  # tracking must never break the real work
            log.warning("could not save usage: %s", e)


@contextmanager
def tracking(db, user_id: str, sermon_id: Optional[str] = None, job_id: Optional[str] = None):
    tracker = Tracker(db, user_id, sermon_id, job_id)
    token = _current.set(tracker)
    try:
        yield tracker
    finally:
        _current.reset(token)
        tracker.flush()


def record(task: str, provider: str, model: str, input_tokens: int = 0, cached_tokens: int = 0,
           output_tokens: int = 0, audio_seconds: float = 0.0) -> Optional[float]:
    """Add one AI call to the current tracker (if any) and return its estimated cost."""
    if audio_seconds:
        cost = pricing.audio_cost(model, audio_seconds)
    else:
        cost = pricing.text_cost(model, input_tokens, cached_tokens, output_tokens)
    tracker = _current.get()
    if tracker is not None:
        tracker.records.append({
            "task": task, "provider": provider, "model": model,
            "input_tokens": int(input_tokens or 0), "cached_tokens": int(cached_tokens or 0),
            "output_tokens": int(output_tokens or 0), "audio_seconds": round(float(audio_seconds or 0), 1),
            "cost_usd": cost,
        })
    return cost


def current() -> Optional[Tracker]:
    return _current.get()
