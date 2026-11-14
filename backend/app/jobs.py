"""Background processing: a sermon is queued as a job, and the browser polls its progress."""
import logging
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Optional

from . import ai, notes, transcripts
from .config import settings
from .db import user_db

log = logging.getLogger("jobs")
_executor = ThreadPoolExecutor(max_workers=max(1, settings.job_workers), thread_name_prefix="sermon-job")
STALE_AFTER = timedelta(minutes=30)


def create_job(db, user_id: str, job_input: dict) -> dict:
    row = db.table("jobs").insert({
        "user_id": user_id, "kind": "sermon", "status": "queued", "step": "Waiting to start",
        "progress": 0, "input": job_input,
    }).execute().data[0]
    return row


def submit(token: str, user_id: str, job_id: str, job_input: dict, upload_path: Optional[str] = None) -> None:
    _executor.submit(run_job, token, user_id, job_id, job_input, upload_path)


def mark_stale(db, jobs: list[dict]) -> list[dict]:
    """A job that stopped reporting (e.g. the server restarted) is shown as failed so it can be retried."""
    now = datetime.now(timezone.utc)
    for j in jobs:
        if j.get("status") in ("queued", "running"):
            try:
                updated = datetime.fromisoformat(str(j["updated_at"]).replace("Z", "+00:00"))
            except (KeyError, ValueError):
                continue
            if now - updated > STALE_AFTER:
                msg = "Processing was interrupted (the server restarted). Retry it."
                db.table("jobs").update({"status": "failed", "error": msg, "step": "Interrupted"}).eq("id", j["id"]).execute()
                j.update(status="failed", error=msg, step="Interrupted")
    return jobs


def _youtube_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def run_job(token: str, user_id: str, job_id: str, job_input: dict, upload_path: Optional[str] = None) -> None:
    db = user_db(token)

    def progress(step: str, pct: int) -> None:
        try:
            db.table("jobs").update({"status": "running", "step": step, "progress": max(0, min(99, pct))}) \
                .eq("id", job_id).execute()
        except Exception as e:  # progress is best effort
            log.warning("progress update failed: %s", e)

    try:
        sermon_id = process(db, user_id, job_input, progress, upload_path)
        db.table("jobs").update({"status": "done", "step": "Notes ready", "progress": 100,
                                 "sermon_id": sermon_id, "error": None}).eq("id", job_id).execute()
    except Exception as e:
        log.exception("job %s failed", job_id)
        message = str(e) or e.__class__.__name__
        try:
            db.table("jobs").update({"status": "failed", "step": "Failed", "error": message[:1000]}) \
                .eq("id", job_id).execute()
        except Exception:
            log.exception("could not record failure for job %s", job_id)
    finally:
        if upload_path:
            shutil.rmtree(os.path.dirname(upload_path), ignore_errors=True)


def process(db, user_id: str, job_input: dict, progress, upload_path: Optional[str] = None) -> str:
    source = job_input.get("source", "youtube")
    model = ai.resolve_model(job_input.get("model"))
    video_id = job_input.get("video_id")
    details = {"title": "", "channel": ""}
    method = source

    # 1. Words with timestamps
    if source == "youtube":
        details = transcripts.video_details(video_id)
        segments, method = transcripts.get_youtube_transcript(video_id, progress)
    elif source == "upload":
        if not upload_path or not os.path.exists(upload_path):
            raise transcripts.TranscriptError("The uploaded file is no longer available. Upload it again.")
        progress("Transcribing the uploaded audio", 10)
        segments = transcripts.transcribe_audio(upload_path, progress)
    elif source == "paste":
        progress("Reading the pasted transcript", 10)
        segments = transcripts.segments_from_text(job_input.get("transcript_text", ""))
    else:
        raise ValueError(f"Unknown source: {source}")

    # 2. Where the sermon starts
    manual_start = transcripts.parse_time(job_input.get("sermon_start_time"))
    if manual_start is not None:
        start_seconds = manual_start
        start_info = {"sermon_start_seconds": start_seconds, "sermon_start_time": transcripts.format_time(start_seconds),
                      "confidence": "manual", "reason": "Set by you"}
    else:
        progress("Finding where the sermon starts", 40)
        start_seconds, start_info = notes.detect_sermon_start(segments, model)

    # 3. Full notes
    progress("Writing full notes (about a minute)", 50)
    result = notes.write_notes(segments, start_seconds, model)

    progress("Saving to your library", 88)
    sermon_text = " ".join(s["text"] for s in segments if s["start"] >= start_seconds)
    full_text = " ".join(s["text"] for s in segments)
    timed = notes.build_timed_chunks(segments, start_seconds)
    duration = int(segments[-1]["start"] + segments[-1].get("duration", 0)) if segments else None
    church_name = job_input.get("church_name") or ""
    if source == "youtube" and not church_name:
        church_name = details.get("channel", "")

    row = {
        "user_id": user_id,
        "video_id": video_id,
        "youtube_url": _youtube_url(video_id) if video_id else None,
        "church_id": job_input.get("church_id"),
        "church_name": church_name,
        "preacher": job_input.get("preacher") or "",
        "title": result.get("title") or details.get("title") or job_input.get("filename") or "Untitled sermon",
        "main_theme": result.get("main_theme", ""),
        "summary": result.get("summary", ""),
        "introduction": result.get("introduction") or {},
        "full_notes": result.get("full_notes") or [],
        "theological_depths": result.get("theological_depths") or [],
        "all_bible_verses": result.get("all_bible_verses") or [],
        "notable_quotes": result.get("notable_quotes") or [],
        "conclusion": result.get("conclusion") or {},
        "practical_applications": result.get("practical_applications") or [],
        "prayer_points": result.get("prayer_points") or [],
        "study_questions": result.get("study_questions") or [],
        "weekly_challenge": result.get("weekly_challenge", ""),
        "related_topics": result.get("related_topics") or [],
        "topics": notes.clean_topics(result),
        "sermon_character": result.get("sermon_character", ""),
        "sermon_start_seconds": start_seconds,
        "sermon_start_info": {**start_info, "transcript_method": method,
                              "small_group_guide": result.get("small_group_guide") or {}},
        "timed_chunks": timed[:240],
        "full_transcript": full_text[:200_000],
        "sermon_transcript": sermon_text[:200_000],
        "model_used": model,
        "source": source,
        "duration_seconds": duration,
    }
    sermon = db.table("sermons").insert(row).execute().data[0]

    # 4. Search index (failure here should not lose the notes)
    try:
        progress("Indexing for Ask", 94)
        index_sermon(db, user_id, sermon["id"], segments, start_seconds)
    except Exception as e:
        log.warning("indexing failed for %s: %s", sermon["id"], e)
    return sermon["id"]


def index_sermon(db, user_id: str, sermon_id: str, segments: list, start_seconds: int) -> int:
    chunks = notes.search_chunks(segments, start_seconds)
    if not chunks:
        return 0
    vectors = None
    try:
        vectors = ai.embed([c["content"] for c in chunks])
    except Exception as e:
        log.warning("embeddings failed, using full-text search only: %s", e)
    rows = []
    for i, c in enumerate(chunks):
        row = {"sermon_id": sermon_id, "user_id": user_id, "chunk_index": i,
               "start_seconds": c["start_seconds"], "content": c["content"]}
        if vectors:
            row["embedding"] = vectors[i]
        rows.append(row)
    for i in range(0, len(rows), 100):
        db.table("sermon_chunks").insert(rows[i:i + 100]).execute()
    return len(rows)
