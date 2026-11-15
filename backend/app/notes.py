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
        result = ai.complete_json(prompt, system, model, max_tokens=600, task="start")
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


CURATION_VERSION = 2

NOTES_SYSTEM = """You are a sermon documentation editor: a theologically trained note-taker who turns a raw sermon
transcript into a curated study document for a church's sermon archive.

CURATE, DON'T SUMMARISE. Someone who missed the service should get the complete teaching from your document.
- Keep every main point, sub-point, argument, scripture, story and application the preacher gave.
- Remove what doesn't teach: worship, announcements, offering, greetings, crowd call-and-response
  ("can I get an amen?", "tell your neighbour..."), repetition, false starts and filler.
- Follow the preacher's own structure. If they number their points, keep that order and wording. If the
  structure is loose, organise by the logical flow of the argument.
- Write clear, edited prose in the present tense that carries the preacher's meaning and tone. Attribute
  claims to the preacher where it matters ("The pastor stresses that...").

BE FAITHFUL.
- Never add teaching, stories, quotes or verses that are not in the transcript. If the preacher paraphrases a
  verse, say it is paraphrased.
- Quote words as spoken only when the transcript clearly has them; lightly clean grammar, never change meaning.
- Fix obvious transcription errors in names and references (e.g. "Fesians one seventeen" -> Ephesians 1:17).
- When the preacher uses Pidgin, Yoruba, Igbo or Hausa, write the notes in English and keep a short original
  phrase in quotes where it carries meaning, with its translation.

Respond with one valid JSON object only: no markdown, no text before or after it."""


def notes_prompt(transcript: str, known: Optional[dict] = None) -> str:
    """The fixed instructions and schema come first and the transcript last, so the long shared prefix
    can be cached by the provider (cached input is billed at 5-10% of the normal rate)."""
    known = known or {}
    hints = "\n".join(f"- {k}: {v}" for k, v in known.items() if v)
    hint_block = f"Details already known about this sermon (trust these):\n{hints}\n\n" if hints else ""
    return f"""Curate this sermon transcript (it is at the end of this message) into a full sermon document. Each transcript line
starts with its [timestamp]; give start_seconds for points, verses, explanations and quotes (e.g. [12:30] -> 750).

Return exactly this JSON structure. Fill every field thoroughly; use "" or [] only when the sermon truly has nothing.
{{
  "title": "The sermon's title as stated, or a faithful title if none was given",
  "sermon_info": {{
    "main_text": "The primary Bible passage, e.g. Ephesians 1:17-18",
    "topic": "The topic in a few words",
    "series": "Series name ONLY if the preacher mentions one, else empty",
    "date_mentioned": "YYYY-MM-DD ONLY if the date of the service is clearly stated, else empty"
  }},
  "overview": "Two short paragraphs: what the message is about, its central argument, and what the preacher wanted the congregation to understand and do",
  "central_message": "The one teaching or revelation that holds the sermon together, in 1-3 sentences",
  "main_theme": "The central truth in one sentence",
  "summary": "A 2-3 sentence description for a library card",
  "introduction": {{"opening": "How the preacher opened", "context": "Background or setting established",
                    "thesis": "The question or claim the sermon sets out to answer"}},
  "main_points": [
    {{"point": "Short title of main point 1", "summary": "2-3 sentences: what this point teaches", "start_seconds": 750}}
  ],
  "full_notes": [
    {{
      "section_number": 1,
      "section_title": "Same title as main point 1 (one section per main point, same order)",
      "start_seconds": 750,
      "full_teaching": "The complete curated teaching for this point in full paragraphs, sub-points included",
      "illustrations": [{{"title": "Short name", "full_story": "The story as told", "spiritual_point": "The truth it illustrates"}}],
      "scriptures_in_this_section": [{{"reference": "Book C:V", "text_as_used": "Verse as quoted or paraphrased",
                                      "how_preacher_used_it": "How it supports this point", "cross_references": ["Book C:V"]}}],
      "key_statements": ["Memorable statements from this section, as spoken"],
      "section_application": "What this point means for the listener"
    }}
  ],
  "all_bible_verses": [{{"reference": "Book C:V", "text_quoted": "Verse as used", "sermon_context": "Where and why it came up",
                        "relevance": "What it establishes in the teaching", "start_seconds": 0, "cross_references": ["Book C:V"]}}],
  "explanations": [{{"title": "Name of the insight", "kind": "explanation | revelation | theological insight | word study | connection",
                    "explanation": "The full explanation exactly as the preacher developed it", "scriptures": ["Book C:V"], "start_seconds": 0}}],
  "notable_quotes": [{{"quote": "Memorable statement as spoken", "context": "What it was making a point about", "start_seconds": 0}}],
  "conclusion": {{"closing_argument": "How the message was brought together", "call_to_action": "The response called for",
                  "closing_prayer_or_charge": "How it closed"}},
  "practical_applications": [{{"application": "A concrete action or mindset", "why_it_matters": "The reason from the sermon",
                              "how_to_do_it": "Practical steps for this week"}}],
  "study_questions": [{{"question": "Reflection or discussion question", "for": "personal | group",
                       "what_to_think_about": "Guidance or a related verse"}}],
  "small_group_guide": {{"icebreaker": "Opening question", "discussion": ["3-5 questions"], "activity": "Something to do together",
                        "closing_prayer": "Prayer to close the meeting"}},
  "prayer_points": [{{"point": "A first-person prayer drawn from the message, e.g. 'Father, open the eyes of my understanding...'",
                     "scripture_basis": "Book C:V"}}],
  "key_takeaways": ["5-8 short, memorable lines: the most important things to remember"],
  "weekly_challenge": "One concrete thing to do this week",
  "related_topics": ["3-8 short topic tags, e.g. Faith, Prayer, Holy Spirit"],
  "sermon_character": "The preacher's style and how the message was delivered"
}}

{hint_block}Transcript:
{transcript}"""


def write_notes(segments: list[Segment], start_seconds: int, model: str, known: Optional[dict] = None,
                premium: bool = False) -> dict:
    transcript = timed_lines(segments, start_seconds)
    if len(transcript) > MAX_PROMPT_CHARS:
        transcript = transcript[:MAX_PROMPT_CHARS]
    if len(transcript) < 200:
        raise ai.AIError("The transcript is too short to write notes from.")
    notes = ai.complete_json(notes_prompt(transcript, known), NOTES_SYSTEM, model, max_tokens=settings.notes_max_tokens,
                             task="notes_premium" if premium else "notes")
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


def _seconds(item) -> Optional[int]:
    try:
        v = int(float(item.get("start_seconds"))) if isinstance(item, dict) and item.get("start_seconds") is not None else None
    except (TypeError, ValueError):
        return None
    return v if v and v > 0 else None


def document_fields(notes: dict) -> dict:
    """Map the AI's JSON onto sermon columns, filling older fields so earlier screens keep working."""
    info = notes.get("sermon_info") or {}
    explanations = [e for e in notes.get("explanations") or [] if isinstance(e, dict)]
    full_notes = notes.get("full_notes") or []
    main_points = [p for p in notes.get("main_points") or [] if isinstance(p, dict) and p.get("point")]
    if not main_points:  # fall back to the detailed sections
        main_points = [{"point": s.get("section_title", ""), "summary": "", "start_seconds": s.get("start_seconds")}
                       for s in full_notes if isinstance(s, dict) and s.get("section_title")]
    date = (info.get("date_mentioned") or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        date = None
    return {
        "main_text": (info.get("main_text") or "").strip(),
        "series_hint": (info.get("series") or "").strip(),
        "date_hint": date,
        "topic": (info.get("topic") or "").strip(),
        "central_message": notes.get("central_message") or notes.get("main_theme") or "",
        "overview": notes.get("overview") or notes.get("summary") or "",
        "main_points": main_points,
        "explanations": explanations,
        "theological_depths": [{"concept": e.get("title", ""), "full_explanation": e.get("explanation", "")}
                               for e in explanations] or (notes.get("theological_depths") or []),
        "key_takeaways": [t for t in notes.get("key_takeaways") or [] if isinstance(t, str) and t.strip()],
    }
