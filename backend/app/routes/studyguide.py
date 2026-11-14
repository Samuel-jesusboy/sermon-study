from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import ai
from ..auth import CurrentUser, get_current_user

router = APIRouter()


class StudyGuideRequest(BaseModel):
    weeks: int = Field(default=4, ge=1, le=12)
    theme: Optional[str] = ""
    model: Optional[str] = None
    sermon_ids: Optional[list[str]] = None
    audience: Optional[str] = "personal"  # personal | small_group | family


def sermon_digest(s: dict) -> str:
    sections = [x.get("section_title", "") for x in (s.get("full_notes") or []) if isinstance(x, dict)][:8]
    verses = [v.get("reference", "") for v in (s.get("all_bible_verses") or []) if isinstance(v, dict)][:10]
    questions = [q.get("question", "") for q in (s.get("study_questions") or []) if isinstance(q, dict)][:3]
    return (f"- \"{s.get('title', 'Untitled')}\" by {s.get('preacher') or 'unknown'}"
            f"{' (' + s['church_name'] + ')' if s.get('church_name') else ''}\n"
            f"  Theme: {s.get('main_theme', '')}\n"
            f"  Summary: {(s.get('summary') or '')[:600]}\n"
            f"  Main points: {' | '.join(sections)}\n"
            f"  Verses: {', '.join(verses)}\n"
            f"  Questions it raised: {' | '.join(questions)}")


@router.post("/generate")
def generate_study_guide(req: StudyGuideRequest, user: CurrentUser = Depends(get_current_user)):
    cols = "id, title, preacher, church_name, summary, main_theme, full_notes, all_bible_verses, study_questions, topics"
    q = user.db.table("sermons").select(cols).eq("user_id", user.id)
    if req.sermon_ids:
        q = q.in_("id", req.sermon_ids)
    elif req.theme:
        q = q.order("created_at", desc=True).limit(60)
    else:
        q = q.order("created_at", desc=True).limit(20)
    sermons = q.execute().data or []
    if req.theme and not req.sermon_ids:
        t = req.theme.lower()
        related = [s for s in sermons if t in (s.get("main_theme") or "").lower()
                   or any(t in x.lower() for x in s.get("topics") or [])
                   or t in (s.get("title") or "").lower() or t in (s.get("summary") or "").lower()]
        sermons = (related or sermons)[:20]
    if not sermons:
        raise HTTPException(status_code=400, detail="Your library is empty. Add some sermons first.")

    audience = {"small_group": "a small group or house fellowship meeting weekly",
                "family": "a family doing devotions together, including children"}.get(req.audience,
                                                                                       "one person's daily devotions")
    system = """You are a Christian curriculum designer. Build practical, scripture-rooted study guides from real
sermons. Each week should build on the last. Refer to the sermons by title so the reader can revisit them."""
    prompt = f"""Create a {req.weeks}-week Bible study guide for {audience}.
{"Focus theme: " + req.theme if req.theme else "Draw out the strongest themes from these sermons."}

Sermons:
{chr(10).join(sermon_digest(s) for s in sermons)}

Format in Markdown. Start with a one-paragraph overview. Then for each week:
## Week N: Title
**Memory verse:** ...
**Theme:** ... (which sermon(s) it comes from)
### Daily readings
- Day 1-5: passage, then one reflection question
### Discuss
3 questions
### This week's challenge
### Prayer focus"""
    try:
        guide = ai.complete(prompt, system, req.model, max_tokens=8000)
    except ai.AIError as e:
        raise HTTPException(status_code=502, detail=str(e))
    model = ai.resolve_model(req.model)
    saved = user.db.table("study_guides").insert({
        "user_id": user.id, "weeks": req.weeks, "theme": req.theme or "", "content": guide,
        "model_used": model, "sermons_count": len(sermons)}).execute().data
    return {"id": saved[0]["id"] if saved else None, "weeks": req.weeks,
            "theme": req.theme or "Drawn from your library", "guide": guide, "model_used": model,
            "sermons_used": len(sermons), "sermon_titles": [s.get("title") for s in sermons]}


@router.get("/list")
def list_study_guides(user: CurrentUser = Depends(get_current_user)):
    return user.db.table("study_guides").select("id, weeks, theme, model_used, sermons_count, created_at") \
        .eq("user_id", user.id).order("created_at", desc=True).execute().data or []


@router.get("/{guide_id}")
def get_study_guide(guide_id: str, user: CurrentUser = Depends(get_current_user)):
    rows = user.db.table("study_guides").select("*").eq("id", guide_id).eq("user_id", user.id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Study guide not found")
    return rows[0]


@router.delete("/{guide_id}")
def delete_study_guide(guide_id: str, user: CurrentUser = Depends(get_current_user)):
    user.db.table("study_guides").delete().eq("id", guide_id).eq("user_id", user.id).execute()
    return {"deleted": guide_id}
