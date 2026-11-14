import os
import tempfile
from collections import Counter
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .. import jobs, transcripts
from ..auth import CurrentUser, get_current_user
from ..config import settings
from ..exporting import sermon_markdown
from ..notes import verse_book

router = APIRouter()

LIST_COLUMNS = ("id, title, church_name, church_id, preacher, main_theme, summary, topics, video_id, source, "
                "is_public, duration_seconds, sermon_start_info, created_at, sermon_date, series, main_text, "
                "central_message, curation_version")


class SermonRequest(BaseModel):
    url: str
    model: Optional[str] = None
    church_name: Optional[str] = ""
    preacher: Optional[str] = ""
    church_id: Optional[str] = None
    sermon_start_time: Optional[str | int] = None
    sermon_date: Optional[str] = None
    series: Optional[str] = ""
    main_text: Optional[str] = ""
    force: bool = False  # process again even if this video is already in the library


class PasteRequest(BaseModel):
    transcript_text: str = Field(min_length=200)
    title: Optional[str] = ""
    model: Optional[str] = None
    church_name: Optional[str] = ""
    preacher: Optional[str] = ""
    sermon_start_time: Optional[str | int] = None
    sermon_date: Optional[str] = None
    series: Optional[str] = ""
    main_text: Optional[str] = ""


class PlaylistRequest(BaseModel):
    playlist_url: str
    model: Optional[str] = None
    church_name: Optional[str] = ""
    church_id: Optional[str] = None
    series: Optional[str] = ""


class RecurateRequest(BaseModel):
    model: Optional[str] = None


class SermonUpdate(BaseModel):
    title: Optional[str] = None
    preacher: Optional[str] = None
    church_name: Optional[str] = None
    topics: Optional[list[str]] = None
    is_public: Optional[bool] = None
    sermon_date: Optional[str] = None
    series: Optional[str] = None
    main_text: Optional[str] = None


def check_limit(user: CurrentUser, adding: int = 1) -> None:
    limit = settings.monthly_sermon_limit
    if limit <= 0:
        return
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    res = user.db.table("jobs").select("id", count="exact").gte("created_at", month_start.isoformat()) \
        .neq("status", "failed").execute()
    used = res.count or 0
    if used + adding > limit:
        raise HTTPException(status_code=429, detail=f"You've reached this month's limit of {limit} sermons.")


def existing_video_ids(user: CurrentUser, video_ids: list[str]) -> dict[str, str]:
    if not video_ids:
        return {}
    res = user.db.table("sermons").select("id, video_id").in_("video_id", video_ids).execute()
    return {r["video_id"]: r["id"] for r in res.data or []}


def clean_date(value: Optional[str]) -> Optional[str]:
    """Accept YYYY-MM-DD (what date inputs send); anything else is ignored."""
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date().isoformat()
    except ValueError:
        raise HTTPException(status_code=400, detail="Use a date like 2026-11-15.")


def queue_video(user: CurrentUser, video_id: str, model, church_name="", preacher="", church_id=None,
                start=None, extra: Optional[dict] = None) -> dict:
    job_input = {"source": "youtube", "video_id": video_id, "url": f"https://www.youtube.com/watch?v={video_id}",
                 "model": model, "church_name": church_name or "", "preacher": preacher or "",
                 "church_id": church_id, "sermon_start_time": start, **(extra or {})}
    job = jobs.create_job(user.db, user.id, job_input)
    jobs.submit(user.token, user.id, job["id"], job_input)
    return job


@router.post("/process")
def process_sermon(req: SermonRequest, user: CurrentUser = Depends(get_current_user)):
    video_id = transcripts.extract_video_id(req.url)
    if not video_id:
        raise HTTPException(status_code=400, detail="That doesn't look like a YouTube video link.")
    if not req.force:
        found = existing_video_ids(user, [video_id])
        if found:
            return {"job": None, "existing_sermon_id": found[video_id]}
    check_limit(user)
    extra = {"sermon_date": clean_date(req.sermon_date), "series": req.series or "", "main_text": req.main_text or ""}
    job = queue_video(user, video_id, req.model, req.church_name, req.preacher, req.church_id, req.sermon_start_time, extra)
    return {"job": job, "existing_sermon_id": None}


@router.post("/paste")
def paste_transcript(req: PasteRequest, user: CurrentUser = Depends(get_current_user)):
    check_limit(user)
    job_input = {"source": "paste", "transcript_text": req.transcript_text[:400_000], "filename": req.title or "",
                 "model": req.model, "church_name": req.church_name or "", "preacher": req.preacher or "",
                 "sermon_start_time": req.sermon_start_time, "sermon_date": clean_date(req.sermon_date),
                 "series": req.series or "", "main_text": req.main_text or ""}
    job = jobs.create_job(user.db, user.id, job_input)
    jobs.submit(user.token, user.id, job["id"], job_input)
    return {"job": job}


ALLOWED_UPLOADS = (".mp3", ".m4a", ".wav", ".aac", ".ogg", ".opus", ".flac", ".webm", ".mp4", ".mov", ".mkv", ".amr")


@router.post("/upload")
async def upload_sermon(file: UploadFile = File(...), model: str = Form(""), church_name: str = Form(""),
                        preacher: str = Form(""), sermon_start_time: str = Form(""),
                        sermon_date: str = Form(""), series: str = Form(""), main_text: str = Form(""),
                        user: CurrentUser = Depends(get_current_user)):
    name = os.path.basename(file.filename or "sermon")
    if not name.lower().endswith(ALLOWED_UPLOADS):
        raise HTTPException(status_code=400, detail="Upload an audio or video file (mp3, m4a, wav, mp4 ...).")
    check_limit(user)
    workdir = tempfile.mkdtemp(prefix="upload_")
    path = os.path.join(workdir, name)
    max_bytes = settings.max_upload_mb * 1024 * 1024
    size = 0
    with open(path, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                out.close()
                import shutil
                shutil.rmtree(workdir, ignore_errors=True)
                raise HTTPException(status_code=413, detail=f"The file is larger than {settings.max_upload_mb} MB.")
            out.write(chunk)
    title = os.path.splitext(name)[0].replace("_", " ").strip()
    job_input = {"source": "upload", "filename": title, "model": model or None, "church_name": church_name,
                 "preacher": preacher, "sermon_start_time": sermon_start_time or None,
                 "sermon_date": clean_date(sermon_date), "series": series, "main_text": main_text}
    job = jobs.create_job(user.db, user.id, job_input)
    jobs.submit(user.token, user.id, job["id"], job_input, upload_path=path)
    return {"job": job}


@router.post("/playlist")
def process_playlist(req: PlaylistRequest, user: CurrentUser = Depends(get_current_user)):
    if not transcripts.extract_playlist_id(req.playlist_url):
        raise HTTPException(status_code=400, detail="That doesn't look like a YouTube playlist link.")
    try:
        videos = transcripts.list_playlist(req.playlist_url, settings.playlist_max_videos)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read the playlist: {str(e)[:200]}")
    found = existing_video_ids(user, [v["video_id"] for v in videos])
    new = [v for v in videos if v["video_id"] not in found]
    check_limit(user, len(new))
    queued = [queue_video(user, v["video_id"], req.model, req.church_name, "", req.church_id,
                          extra={"series": req.series or ""}) for v in new]
    return {"queued": len(queued), "skipped_existing": len(found), "jobs": queued}


@router.get("/list")
def list_sermons(limit: int = 50, offset: int = 0, q: str = "", topic: str = "", church: str = "", series: str = "",
                 user: CurrentUser = Depends(get_current_user)):
    query = user.db.table("sermons").select(LIST_COLUMNS).eq("user_id", user.id) \
        .order("created_at", desc=True).range(offset, offset + min(limit, 200) - 1)
    if topic:
        query = query.contains("topics", [topic])
    if church:
        query = query.eq("church_name", church)
    if series:
        query = query.eq("series", series)
    safe = q.replace(",", " ").replace("(", " ").replace(")", " ").replace("*", " ").strip() if q else ""
    if safe:
        query = query.or_(f"title.ilike.*{safe}*,summary.ilike.*{safe}*,main_theme.ilike.*{safe}*,"
                          f"preacher.ilike.*{safe}*,series.ilike.*{safe}*,main_text.ilike.*{safe}*,"
                          f"central_message.ilike.*{safe}*")
    rows = query.execute().data or []
    if safe and offset == 0:
        rows = add_transcript_matches(user, safe, rows)
    return rows


def add_transcript_matches(user: CurrentUser, q: str, rows: list[dict]) -> list[dict]:
    """Also find sermons where the words were *said*, with the minute and a snippet."""
    try:
        hits = user.db.rpc("search_sermon_chunks", {"query": q, "match_count": 40}).execute().data or []
    except Exception:
        return rows
    best: dict[str, dict] = {}
    for h in hits:
        if h["sermon_id"] not in best:
            best[h["sermon_id"]] = h
    if not best:
        return rows
    by_id = {r["id"]: r for r in rows}
    missing = [sid for sid in best if sid not in by_id]
    if missing:
        extra = user.db.table("sermons").select(LIST_COLUMNS).in_("id", missing).eq("user_id", user.id) \
            .execute().data or []
        for r in extra:
            by_id[r["id"]] = r
            rows.append(r)
    for sid, h in best.items():
        if sid in by_id:
            secs = int(h.get("start_seconds") or 0)
            by_id[sid]["transcript_match"] = {"seconds": secs, "time": transcripts.format_time(secs),
                                              "excerpt": _snippet(h.get("content", ""), q)}
    return rows


def _snippet(text: str, q: str, width: int = 220) -> str:
    low, words = text.lower(), [w for w in q.lower().split() if len(w) > 2]
    pos = min((low.find(w) for w in words if low.find(w) >= 0), default=0)
    start = max(0, pos - width // 3)
    out = text[start:start + width].strip()
    return ("…" if start > 0 else "") + out + ("…" if start + width < len(text) else "")


@router.get("/topics")
def topic_index(user: CurrentUser = Depends(get_current_user)):
    """Counts for browsing: topics, Bible books preached from, churches and preachers."""
    rows = user.db.table("sermons").select("topics, all_bible_verses, church_name, preacher, series") \
        .eq("user_id", user.id).limit(1000).execute().data or []
    topics, books, churches, preachers, series = Counter(), Counter(), Counter(), Counter(), Counter()
    for r in rows:
        topics.update(r.get("topics") or [])
        seen = set()
        for v in r.get("all_bible_verses") or []:
            b = verse_book(v.get("reference", "") if isinstance(v, dict) else str(v))
            if b and b not in seen:
                seen.add(b)
                books[b] += 1
        if r.get("church_name"):
            churches[r["church_name"]] += 1
        if r.get("preacher"):
            preachers[r["preacher"]] += 1
        if r.get("series"):
            series[r["series"]] += 1

    def top(c: Counter, n=40):
        return [{"name": k, "count": v} for k, v in c.most_common(n)]
    return {"topics": top(topics), "books": top(books, 66), "churches": top(churches), "preachers": top(preachers),
            "series": top(series), "total": len(rows)}


@router.get("/by-book/{book}")
def sermons_by_book(book: str, user: CurrentUser = Depends(get_current_user)):
    rows = user.db.table("sermons").select(LIST_COLUMNS + ", all_bible_verses").eq("user_id", user.id) \
        .order("created_at", desc=True).limit(500).execute().data or []
    target = book.strip().lower()
    out = []
    for r in rows:
        refs = [v.get("reference", "") for v in r.get("all_bible_verses") or [] if isinstance(v, dict)]
        matching = [ref for ref in refs if (verse_book(ref) or "").lower() == target]
        if matching:
            r.pop("all_bible_verses", None)
            r["matching_verses"] = matching
            out.append(r)
    return out


@router.get("/{sermon_id}")
def get_sermon(sermon_id: str, user: CurrentUser = Depends(get_current_user)):
    rows = user.db.table("sermons").select("*").eq("id", sermon_id).eq("user_id", user.id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Sermon not found")
    return rows[0]


@router.patch("/{sermon_id}")
def update_sermon(sermon_id: str, req: SermonUpdate, user: CurrentUser = Depends(get_current_user)):
    changes = {k: v for k, v in req.model_dump().items() if v is not None}
    if not changes:
        raise HTTPException(status_code=400, detail="Nothing to update")
    if "sermon_date" in changes:
        changes["sermon_date"] = clean_date(changes["sermon_date"]) if changes["sermon_date"] else None
    rows = user.db.table("sermons").update(changes).eq("id", sermon_id).eq("user_id", user.id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Sermon not found")
    r = rows[0]
    return {k: r.get(k) for k in ("id", "title", "preacher", "church_name", "topics", "is_public",
                                  "sermon_date", "series", "main_text")}


@router.post("/{sermon_id}/recurate")
def recurate_sermon(sermon_id: str, req: RecurateRequest, user: CurrentUser = Depends(get_current_user)):
    """Rewrite a sermon's document from its saved transcript, in the latest format."""
    get_sermon(sermon_id, user)  # 404 if it isn't yours
    job_input = {"source": "recurate", "sermon_id": sermon_id, "model": req.model}
    job = jobs.create_job(user.db, user.id, job_input)
    jobs.submit(user.token, user.id, job["id"], job_input)
    return {"job": job}


@router.get("/{sermon_id}/markdown")
def export_markdown(sermon_id: str, user: CurrentUser = Depends(get_current_user)):
    sermon = get_sermon(sermon_id, user)
    return {"filename": _filename(sermon.get("title")), "markdown": sermon_markdown(sermon)}


def _filename(title: Optional[str]) -> str:
    base = "".join(c if c.isalnum() or c in " -_" else "" for c in (title or "sermon")).strip() or "sermon"
    return base[:80].replace(" ", "-").lower() + ".md"


@router.delete("/{sermon_id}")
def delete_sermon(sermon_id: str, user: CurrentUser = Depends(get_current_user)):
    rows = user.db.table("sermons").delete().eq("id", sermon_id).eq("user_id", user.id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Sermon not found")
    return {"deleted": sermon_id}
