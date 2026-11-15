"""What your AI usage has cost: this month, recent days, by job and by model."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from ..auth import CurrentUser, get_current_user

router = APIRouter()

TASK_LABELS = {
    "notes": "Sermon documents", "notes_premium": "Sermon documents (premium)", "start": "Finding the sermon start",
    "ask": "Ask", "verse": "Verse explanations", "guide": "Study guides", "embed": "Search indexing",
    "transcribe": "Audio transcription",
}


@router.get("")
def usage_summary(days: int = 30, user: CurrentUser = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    since = min(month_start, now - timedelta(days=max(1, min(days, 365))))
    rows = user.db.table("ai_usage").select(
        "created_at, task, provider, model, input_tokens, cached_tokens, output_tokens, audio_seconds, cost_usd, sermon_id"
    ).eq("user_id", user.id).gte("created_at", since.isoformat()).order("created_at", desc=True).limit(20000) \
        .execute().data or []

    window_start = now - timedelta(days=days)
    month = [r for r in rows if _ts(r) >= month_start]
    window = [r for r in rows if _ts(r) >= window_start]

    def total(rs):
        return round(sum(float(r.get("cost_usd") or 0) for r in rs), 4)

    by_task, by_model = defaultdict(lambda: {"cost": 0.0, "calls": 0}), defaultdict(lambda: {"cost": 0.0, "calls": 0, "tokens": 0, "audio_seconds": 0.0})
    by_day = defaultdict(float)
    for r in window:
        c = float(r.get("cost_usd") or 0)
        by_task[r["task"]]["cost"] += c
        by_task[r["task"]]["calls"] += 1
        m = by_model[r["model"]]
        m["cost"] += c
        m["calls"] += 1
        m["tokens"] += int(r.get("input_tokens") or 0) + int(r.get("output_tokens") or 0)
        m["audio_seconds"] += float(r.get("audio_seconds") or 0)
        by_day[_ts(r).date().isoformat()] += c

    sermon_ids = {r["sermon_id"] for r in window if r.get("sermon_id")}
    notes_calls = [r for r in window if r["task"] in ("notes", "notes_premium")]
    sermons_count = len({r["sermon_id"] for r in notes_calls if r.get("sermon_id")}) or len(notes_calls)
    sermon_cost = sum(float(r.get("cost_usd") or 0) for r in window if r.get("sermon_id")
                      and r["task"] in ("notes", "notes_premium", "start", "embed", "transcribe"))

    recent = []
    if sermon_ids:
        recent = user.db.table("sermons").select("id, title, cost_usd, models_used, created_at") \
            .eq("user_id", user.id).in_("id", list(sermon_ids)[:200]).order("created_at", desc=True) \
            .limit(15).execute().data or []

    return {
        "days": days,
        "month_total": total(month),
        "window_total": total(window),
        "calls": len(window),
        "unpriced_calls": sum(1 for r in window if r.get("cost_usd") is None),
        "avg_cost_per_sermon": round(sermon_cost / sermons_count, 4) if sermons_count else None,
        "by_task": sorted(({"task": k, "label": TASK_LABELS.get(k, k), "cost": round(v["cost"], 4), "calls": v["calls"]}
                           for k, v in by_task.items()), key=lambda x: -x["cost"]),
        "by_model": sorted(({"model": k, "cost": round(v["cost"], 4), "calls": v["calls"], "tokens": v["tokens"],
                             "audio_minutes": round(v["audio_seconds"] / 60, 1)}
                            for k, v in by_model.items()), key=lambda x: -x["cost"]),
        "by_day": [{"date": d, "cost": round(c, 4)} for d, c in sorted(by_day.items())],
        "recent_sermons": [{"id": s["id"], "title": s.get("title"), "cost_usd": float(s.get("cost_usd") or 0),
                            "models_used": s.get("models_used") or {}} for s in recent],
    }


def _ts(r) -> datetime:
    return datetime.fromisoformat(str(r["created_at"]).replace("Z", "+00:00"))
