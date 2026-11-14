from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import transcripts
from ..auth import CurrentUser, get_current_user
from .sermons import check_limit, existing_video_ids, queue_video

router = APIRouter()
SYNC_EVERY = timedelta(hours=12)


class Church(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    youtube_channel_url: str = Field(min_length=10)
    description: Optional[str] = ""
    playlist_url: Optional[str] = ""
    auto_import: bool = False


class ChurchUpdate(BaseModel):
    name: Optional[str] = None
    youtube_channel_url: Optional[str] = None
    description: Optional[str] = None
    playlist_url: Optional[str] = None
    auto_import: Optional[bool] = None


@router.get("/")
def list_churches(user: CurrentUser = Depends(get_current_user)):
    churches = user.db.table("churches").select("*").eq("user_id", user.id).order("created_at").execute().data or []
    counts = user.db.table("sermons").select("church_id").eq("user_id", user.id).not_.is_("church_id", "null") \
        .limit(5000).execute().data or []
    tally: dict[str, int] = {}
    for r in counts:
        tally[r["church_id"]] = tally.get(r["church_id"], 0) + 1
    for c in churches:
        c["sermon_count"] = tally.get(c["id"], 0)
    return churches


@router.post("/")
def add_church(church: Church, user: CurrentUser = Depends(get_current_user)):
    row = {**church.model_dump(), "user_id": user.id}
    return user.db.table("churches").insert(row).execute().data[0]


@router.patch("/{church_id}")
def update_church(church_id: str, req: ChurchUpdate, user: CurrentUser = Depends(get_current_user)):
    changes = {k: v for k, v in req.model_dump().items() if v is not None}
    rows = user.db.table("churches").update(changes).eq("id", church_id).eq("user_id", user.id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Church not found")
    return rows[0]


@router.delete("/{church_id}")
def delete_church(church_id: str, user: CurrentUser = Depends(get_current_user)):
    user.db.table("churches").delete().eq("id", church_id).eq("user_id", user.id).execute()
    return {"deleted": church_id}


@router.get("/{church_id}/sermons")
def get_church_sermons(church_id: str, user: CurrentUser = Depends(get_current_user)):
    rows = user.db.table("churches").select("*").eq("id", church_id).eq("user_id", user.id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Church not found")
    church = rows[0]
    sermons = user.db.table("sermons").select("id, title, summary, main_theme, preacher, topics, created_at") \
        .eq("user_id", user.id).or_(f"church_id.eq.{church_id},church_name.eq.\"{church['name']}\"") \
        .order("created_at", desc=True).execute().data or []
    return {"church": church, "sermons": sermons}


def _check(user: CurrentUser, church: dict, model: Optional[str], limit: int = 5) -> dict:
    url = church.get("playlist_url") or church["youtube_channel_url"]
    try:
        videos = transcripts.latest_channel_videos(url, limit)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read {church['name']}'s channel: {str(e)[:200]}")
    found = existing_video_ids(user, [v["video_id"] for v in videos])
    new = [v for v in videos if v["video_id"] not in found]
    if new:
        check_limit(user, len(new))
    jobs = [queue_video(user, v["video_id"], model, church["name"], "", church["id"]) for v in new]
    user.db.table("churches").update({"last_checked_at": datetime.now(timezone.utc).isoformat()}) \
        .eq("id", church["id"]).execute()
    return {"church_id": church["id"], "queued": len(jobs), "already_in_library": len(found),
            "titles": [v["title"] for v in new]}


@router.post("/{church_id}/check")
def check_for_new_sermons(church_id: str, limit: int = 5, model: Optional[str] = None,
                          user: CurrentUser = Depends(get_current_user)):
    rows = user.db.table("churches").select("*").eq("id", church_id).eq("user_id", user.id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Church not found")
    return _check(user, rows[0], model, max(1, min(limit, 15)))


@router.post("/sync")
def sync_auto_import(user: CurrentUser = Depends(get_current_user)):
    """Called when the app opens: checks churches with auto-import on, at most every 12 hours each."""
    churches = user.db.table("churches").select("*").eq("user_id", user.id).eq("auto_import", True).execute().data or []
    now = datetime.now(timezone.utc)
    results = []
    for c in churches:
        last = c.get("last_checked_at")
        if last:
            try:
                if now - datetime.fromisoformat(str(last).replace("Z", "+00:00")) < SYNC_EVERY:
                    continue
            except ValueError:
                pass
        try:
            results.append(_check(user, c, None, 3))
        except HTTPException as e:
            results.append({"church_id": c["id"], "error": e.detail})
    return {"checked": len(results), "queued": sum(r.get("queued", 0) for r in results), "results": results}
