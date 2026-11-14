"""Read-only access to sermons their owner chose to share (no sign-in needed)."""
from fastapi import APIRouter, HTTPException

from ..db import anon_db

router = APIRouter()

PUBLIC_COLUMNS = ("id, title, church_name, preacher, main_theme, summary, introduction, full_notes, "
                  "theological_depths, all_bible_verses, notable_quotes, conclusion, practical_applications, "
                  "prayer_points, study_questions, weekly_challenge, topics, video_id, sermon_start_seconds, "
                  "sermon_start_info, timed_chunks, created_at")


@router.get("/sermons/{sermon_id}")
def shared_sermon(sermon_id: str):
    try:
        rows = anon_db().table("sermons").select(PUBLIC_COLUMNS).eq("id", sermon_id).eq("is_public", True) \
            .limit(1).execute().data
    except Exception:
        rows = None
    if not rows:
        raise HTTPException(status_code=404, detail="This sermon isn't shared, or the link is wrong.")
    return rows[0]
