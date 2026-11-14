from fastapi import APIRouter, Depends, HTTPException

from .. import jobs
from ..auth import CurrentUser, get_current_user

router = APIRouter()

COLUMNS = "id, status, step, progress, sermon_id, error, created_at, updated_at, input->>source, " \
          "input->>video_id, input->>filename, input->>church_name"


@router.get("")
def list_jobs(active: bool = False, user: CurrentUser = Depends(get_current_user)):
    q = user.db.table("jobs").select(COLUMNS).eq("user_id", user.id).order("created_at", desc=True).limit(30)
    if active:
        q = q.in_("status", ["queued", "running"])
    return jobs.mark_stale(user.db, q.execute().data or [])


@router.get("/{job_id}")
def get_job(job_id: str, user: CurrentUser = Depends(get_current_user)):
    rows = user.db.table("jobs").select(COLUMNS).eq("id", job_id).eq("user_id", user.id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs.mark_stale(user.db, rows)[0]


@router.post("/{job_id}/retry")
def retry_job(job_id: str, user: CurrentUser = Depends(get_current_user)):
    rows = user.db.table("jobs").select("id, status, input").eq("id", job_id).eq("user_id", user.id) \
        .limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Job not found")
    job = rows[0]
    if job["status"] != "failed":
        raise HTTPException(status_code=400, detail="Only failed jobs can be retried.")
    if (job["input"] or {}).get("source") == "upload":
        raise HTTPException(status_code=400, detail="Uploaded files aren't kept. Please upload the file again.")
    user.db.table("jobs").update({"status": "queued", "step": "Waiting to start", "progress": 0, "error": None}) \
        .eq("id", job_id).execute()
    jobs.submit(user.token, user.id, job_id, job["input"])
    return {"retried": job_id}


@router.delete("/{job_id}")
def dismiss_job(job_id: str, user: CurrentUser = Depends(get_current_user)):
    user.db.table("jobs").delete().eq("id", job_id).eq("user_id", user.id).neq("status", "running").execute()
    return {"deleted": job_id}
