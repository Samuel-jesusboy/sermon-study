"""Ask questions of your sermon library. Answers cite the sermon and the minute it came from."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import ai, usage
from ..auth import CurrentUser, get_current_user
from ..transcripts import format_time
from .bible import fetch_passage

log = logging.getLogger("ask")
router = APIRouter()


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    model: Optional[str] = None
    sermon_id: Optional[str] = None


def retrieve(user: CurrentUser, question: str, sermon_id: Optional[str] = None, k: int = 8) -> list[dict]:
    """Best-matching transcript passages: vector search when available, else full-text search."""
    db = user.db
    if sermon_id:
        rows = db.table("sermon_chunks").select("sermon_id, chunk_index, start_seconds, content") \
            .eq("sermon_id", sermon_id).order("chunk_index").limit(400).execute().data or []
        if not rows:
            return []
        vectors = None
        try:
            vectors = ai.embed([question])
        except Exception as e:
            log.warning("embedding failed: %s", e)
        if vectors:
            matched = db.rpc("match_sermon_chunks", {"query_embedding": vectors[0], "match_count": 50}).execute().data
            keep = [m for m in matched or [] if m["sermon_id"] == sermon_id][:k]
            if keep:
                return keep
        words = {w.lower().strip("?.,!") for w in question.split() if len(w) > 3}
        scored = sorted(rows, key=lambda r: -sum(w in r["content"].lower() for w in words))
        return scored[:k]

    try:
        vectors = ai.embed([question])
    except Exception as e:
        log.warning("embedding failed: %s", e)
        vectors = None
    if vectors:
        matched = db.rpc("match_sermon_chunks", {"query_embedding": vectors[0], "match_count": k}).execute().data
        if matched:
            return matched
    matched = db.rpc("search_sermon_chunks", {"query": question, "match_count": k}).execute().data
    if matched:
        return matched
    # Loosen: any of the important words
    words = [w.strip("?.,!\"'") for w in question.split() if len(w) > 3]
    if words:
        matched = db.rpc("search_sermon_chunks", {"query": " or ".join(words[:8]), "match_count": k}).execute().data
    return matched or []


def sermon_titles(user: CurrentUser, ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    rows = user.db.table("sermons").select("id, title, preacher, church_name, video_id, main_theme, summary") \
        .in_("id", list(set(ids))).eq("user_id", user.id).execute().data or []
    return {r["id"]: r for r in rows}


def build_sources(passages: list[dict], meta: dict[str, dict]) -> list[dict]:
    sources = []
    for p in passages:
        s = meta.get(p["sermon_id"])
        if not s:
            continue
        secs = int(p.get("start_seconds") or 0)
        sources.append({
            "n": len(sources) + 1,
            "sermon_id": s["id"],
            "title": s.get("title") or "Untitled sermon",
            "preacher": s.get("preacher") or "",
            "church_name": s.get("church_name") or "",
            "start_seconds": secs,
            "time": format_time(secs),
            "video_url": f"https://www.youtube.com/watch?v={s['video_id']}&t={secs}s" if s.get("video_id") else None,
            "excerpt": p["content"][:1200],
        })
    return sources


SYSTEM = """You are a warm, careful Christian study assistant. You answer from the user's own sermon library.
Rules:
- Ground your answer in the numbered sermon excerpts. Cite them inline like [1] or [2][3].
- Say plainly when the library doesn't cover something, then you may add general Biblical teaching, labelled
  as such ("Beyond your sermons, ...").
- Never invent what a preacher said. Quote only words that appear in the excerpts.
- Cite Bible references (Book Chapter:Verse) where relevant. End with one practical application.
Use short paragraphs and Markdown."""


@router.post("/")
def ask(req: AskRequest, user: CurrentUser = Depends(get_current_user)):
    with usage.tracking(user.db, user.id, sermon_id=req.sermon_id) as t:
        out = _ask(req, user)
    return {**out, "cost_usd": t.total_cost}


def _ask(req: AskRequest, user: CurrentUser) -> dict:
    passages = retrieve(user, req.question, req.sermon_id)
    meta = sermon_titles(user, [p["sermon_id"] for p in passages])
    sources = build_sources(passages, meta)
    if sources:
        context = "\n\n".join(
            f"[{s['n']}] \"{s['title']}\" by {s['preacher'] or 'unknown'} at {s['time']}:\n{s['excerpt']}"
            for s in sources)
    else:
        context = "(No matching passages were found in the user's sermon library.)"
    prompt = f"Question: {req.question}\n\nSermon excerpts:\n{context}"
    try:
        answer = ai.complete(prompt, SYSTEM, req.model, max_tokens=2000, task="ask")
    except ai.AIError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"question": req.question, "answer": answer, "sources": sources,
            "model_used": ai.model_for(ai.resolve_model(req.model), "ask"), "library_matches": len(sources)}


@router.post("/explain-verse")
async def explain_verse(req: AskRequest, user: CurrentUser = Depends(get_current_user)):
    with usage.tracking(user.db, user.id) as t:
        out = await _explain(req, user)
    return {**out, "cost_usd": t.total_cost}


async def _explain(req: AskRequest, user: CurrentUser) -> dict:
    verse_text = ""
    try:
        passage = await fetch_passage(req.question, "kjv")
        verse_text = " ".join(f"{v['verse']} {v['text']}" for v in passage["verses"])[:3000]
        reference = passage.get("reference", req.question)
    except Exception:
        reference = req.question
    passages = retrieve(user, reference, None, k=6)
    meta = sermon_titles(user, [p["sermon_id"] for p in passages])
    sources = build_sources(passages, meta)
    context = "\n\n".join(f"[{s['n']}] \"{s['title']}\" at {s['time']}:\n{s['excerpt']}" for s in sources) \
        or "(No sermons in the library mention this passage.)"
    system = """You are a Christian Bible teacher. Explain the passage: its plain meaning, its context in the
book, key words, cross-references, and how it applies today. If the user's sermons below touch on it,
connect to them and cite like [1]; otherwise don't mention sermons. Use Markdown with short sections."""
    prompt = f"Passage: {reference}\nText (KJV): {verse_text or '(look up the passage)'}\n\nSermons:\n{context}"
    try:
        answer = ai.complete(prompt, system, req.model, max_tokens=2000, task="verse")
    except ai.AIError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"verse_query": req.question, "reference": reference, "verse_text": verse_text,
            "explanation": answer, "sources": sources,
            "model_used": ai.model_for(ai.resolve_model(req.model), "verse")}
