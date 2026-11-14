"""Turning a timestamped transcript into full sermon notes, timed chunks and search chunks."""
import re
from typing import Optional

from . import ai
from .config import settings
from .transcripts import Segment, format_time

MAX_PROMPT_CHARS = 150_000  # about a 2.5-hour sermon; models used here all take this comfortably


def timed_lines(segments: list[Segment], start_seconds: int = 0, every: int = 30) -> str:
    """Group segments into lines like '[12:30] words...' about every 30 seconds."""
    lines, current, line_start = [], [], None
    for s in segments:
        if s["start"] < start_seconds:
            continue
        if line_start is None:
            line_start = s["start"]
        if s["start"] - line_start >= every and current:
            lines.append(f"[{format_time(line_start)}] {' '.join(current)}")
            current, line_start = [], s["start"]
        current.append(s["text"])
    if current:
        lines.append(f"[{format_time(line_start or 0)}] {' '.join(current)}")
    return "\n".join(lines)


def build_timed_chunks(segments: list[Segment], start_seconds: int = 0, chunk_size: int = 60) -> list[dict]:
    """60-second blocks of transcript for the clickable transcript view."""
    relevant = [s for s in segments if s["start"] >= start_seconds]
    chunks: list[dict] = []
    if not relevant:
        return chunks
    current = {"start": relevant[0]["start"], "text": []}
    for seg in relevant:
        if seg["start"] - current["start"] >= chunk_size and current["text"]:
            chunks.append({"time": format_time(current["start"]), "seconds": int(current["start"]),
                           "text": " ".join(current["text"]).strip()})
            current = {"start": seg["start"], "text": []}
        current["text"].append(seg["text"])
    if current["text"]:
        chunks.append({"time": format_time(current["start"]), "seconds": int(current["start"]),
                       "text": " ".join(current["text"]).strip()})
    return chunks


def search_chunks(segments: list[Segment], start_seconds: int = 0, target_chars: int = 900) -> list[dict]:
    """About 90-second passages, each with its start time, for Ask to search and cite."""
    out, buf, buf_start = [], [], None
    size = 0
    for seg in segments:
        if seg["start"] < start_seconds:
            continue
        if buf_start is None:
            buf_start = seg["start"]
        buf.append(seg["text"])
        size += len(seg["text"]) + 1
        if size >= target_chars:
            out.append({"start_seconds": int(buf_start), "content": " ".join(buf)})
            buf, buf_start, size = [], None, 0
    if buf:
        out.append({"start_seconds": int(buf_start or 0), "content": " ".join(buf)})
    return out


def detect_sermon_start(segments: list[Segment], model: str) -> tuple[int, dict]:
    """Ask the AI where worship and announcements end and the teaching begins."""
    sample = timed_lines([s for s in segments if s["start"] <= 2400], 0, every=20)[:12000]
    if not sample:
        return 0, {"sermon_start_seconds": 0, "sermon_start_time": "0:00", "confidence": "low",
                   "reason": "No transcript to analyse"}
    system = "You find where the sermon begins in a church service transcript. Reply with JSON only."
    prompt = f"""Find the timestamp where the actual sermon or Bible teaching begins, not worship, announcements,
offering or greetings. Signals: "turn your Bible to", "our text today", the preacher stating a title or topic,
a clear shift from casual talk to focused teaching. If the recording starts with the sermon, answer 0.

Transcript:
{sample}

Reply with JSON only:
{{"sermon_start_seconds": <integer>, "sermon_start_time": "<like 12:34>", "confidence": "high|medium|low",
"reason": "<the signal you found>"}}"""
    try:
        result = ai.complete_json(prompt, system, model, max_tokens=600)
        seconds = max(0, int(float(result.get("sermon_start_seconds") or 0)))
        last = segments[-1]["start"] if segments else 0
        if seconds > last:
            seconds = 0
        result["sermon_start_seconds"] = seconds
        result["sermon_start_time"] = format_time(seconds)
        return seconds, result
    except Exception:
        return 0, {"sermon_start_seconds": 0, "sermon_start_time": "0:00", "confidence": "low",
                   "reason": "Could not detect automatically"}


NOTES_SYSTEM = """You are an expert Christian theologian, Bible teacher and sermon note-taker.
Produce FULL, COMPREHENSIVE sermon notes, not a summary: someone reading them months later should get the whole
teaching without watching the video. Write every point out, tell every illustration, explain every scripture in
context. Stay faithful to what the preacher actually said; do not invent content, quotes or verses.
Write the notes in English even if the sermon is in another language or mixes languages (e.g. Pidgin or Yoruba).
Respond with one valid JSON object only. No markdown, no text outside the JSON."""


def notes_prompt(transcript: str) -> str:
    return f"""Produce full, detailed sermon notes from this transcript. Each line starts with its [timestamp].
Use those timestamps: give each section the second where it starts (e.g. [12:30] -> 750).

Transcript:
{transcript}

Return exactly this JSON structure, every field thorough and complete:
{{
  "title": "Sermon title (infer it if not stated)",
  "main_theme": "The single central truth of the message in one sentence",
  "summary": "5-8 sentence summary: what was taught, why it matters, what the listener is called to do",
  "introduction": {{"opening": "How the preacher opened", "context": "Background set up before the main teaching",
                    "thesis": "The main statement or question the sermon answers"}},
  "full_notes": [
    {{
      "section_title": "Title of this main point",
      "section_number": 1,
      "start_seconds": 750,
      "full_teaching": "The complete teaching for this point in full paragraphs",
      "illustrations": [{{"title": "Short name", "full_story": "The story as told", "spiritual_point": "The truth it establishes"}}],
      "scriptures_in_this_section": [{{"reference": "Book Chapter:Verse", "text_as_used": "Verse as quoted",
                                      "how_preacher_used_it": "How it was taught and applied", "cross_references": ["Book C:V"]}}],
      "key_statements": ["Notable statements, as close to verbatim as possible"],
      "section_application": "What this point means for the listener's life"
    }}
  ],
  "theological_depths": [{{"concept": "Doctrine addressed", "full_explanation": "How the preacher taught it"}}],
  "all_bible_verses": [{{"reference": "Book Chapter:Verse", "text_quoted": "Verse as used",
                        "sermon_context": "Why it was used", "start_seconds": 0, "cross_references": ["Book C:V"]}}],
  "notable_quotes": [{{"quote": "Exact or near-exact quote", "context": "What it was making a point about", "start_seconds": 0}}],
  "conclusion": {{"closing_argument": "How it was brought together", "call_to_action": "The response called for",
                  "closing_prayer_or_charge": "How it closed"}},
  "practical_applications": [{{"application": "Concrete action or mindset shift", "why_it_matters": "Why",
                              "how_to_do_it": "Practical steps"}}],
  "prayer_points": [{{"point": "Prayer focus from the message", "scripture_basis": "A verse to pray from"}}],
  "study_questions": [{{"question": "Reflection or discussion question", "what_to_think_about": "Guidance"}}],
  "small_group_guide": {{"icebreaker": "Opening question", "discussion": ["3-5 discussion questions"],
                        "activity": "Something to do together", "closing_prayer": "Prayer to close the meeting"}},
  "weekly_challenge": "One concrete thing to do this week",
  "related_topics": ["3-8 short topic tags, e.g. Faith, Prayer, Marriage, Holy Spirit"],
  "sermon_character": "The preacher's style and how the message was delivered"
}}"""


def write_notes(segments: list[Segment], start_seconds: int, model: str) -> dict:
    transcript = timed_lines(segments, start_seconds)
    if len(transcript) > MAX_PROMPT_CHARS:
        transcript = transcript[:MAX_PROMPT_CHARS]
    if len(transcript) < 200:
        raise ai.AIError("The transcript is too short to write notes from.")
    notes = ai.complete_json(notes_prompt(transcript), NOTES_SYSTEM, model, max_tokens=settings.notes_max_tokens)
    if not isinstance(notes.get("full_notes"), list):
        notes["full_notes"] = []
    return notes


def clean_topics(notes: dict) -> list[str]:
    """Short, title-cased, de-duplicated topic tags for browsing."""
    raw = list(notes.get("related_topics") or [])
    seen, out = set(), []
    for t in raw:
        if not isinstance(t, str):
            continue
        tag = re.sub(r"\s+", " ", t).strip(" .,-").strip()
        if not tag or len(tag) > 40:
            continue
        tag = tag[:1].upper() + tag[1:]
        key = tag.lower()
        if key not in seen:
            seen.add(key)
            out.append(tag)
    return out[:10]


def verse_book(reference: str) -> Optional[str]:
    m = re.match(r"\s*((?:[1-3]\s*)?[A-Za-z][A-Za-z ]*?)\s+\d", reference or "")
    return m.group(1).strip().title() if m else None
