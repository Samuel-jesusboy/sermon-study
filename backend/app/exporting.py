"""Sermon documentation as Markdown, in the 11-section structure (also used for copy/paste and download)."""
from datetime import date

from .transcripts import format_time


def _t(item, key: str = "start_seconds") -> str:
    s = item.get(key) if isinstance(item, dict) else None
    try:
        s = int(float(s)) if s is not None else None
    except (TypeError, ValueError):
        s = None
    return f" ({format_time(s)})" if s and s > 0 else ""


def _date(value) -> str:
    if not value:
        return ""
    try:
        d = date.fromisoformat(str(value)[:10])
        return f"{d.day} {d.strftime('%B %Y')}"
    except ValueError:
        return str(value)


def document_view(s: dict) -> dict:
    """The 11 sections, with fallbacks so sermons processed before v2 still read well."""
    intro = s.get("introduction") or {}
    full_notes = [x for x in s.get("full_notes") or [] if isinstance(x, dict)]
    points = [p for p in s.get("main_points") or [] if isinstance(p, dict)]
    if not points:
        points = [{"point": x.get("section_title", ""), "summary": "", "start_seconds": x.get("start_seconds")}
                  for x in full_notes if x.get("section_title")]
    explanations = [e for e in s.get("explanations") or [] if isinstance(e, dict)]
    if not explanations:
        explanations = [{"title": t.get("concept", ""), "explanation": t.get("full_explanation", ""), "kind": ""}
                        for t in s.get("theological_depths") or [] if isinstance(t, dict)]
    illustrations = [dict(ill, section=x.get("section_title", "")) for x in full_notes
                     for ill in x.get("illustrations") or [] if isinstance(ill, dict)]
    verses = [v for v in s.get("all_bible_verses") or [] if isinstance(v, dict)]
    main_text = s.get("main_text") or (verses[0].get("reference") if verses else "")
    takeaways = [t for t in s.get("key_takeaways") or [] if t]
    if not takeaways:
        takeaways = [p.get("point") for p in points if p.get("point")][:6]
    return {
        "info": [("Preacher", s.get("preacher")), ("Church", s.get("church_name")), ("Date", _date(s.get("sermon_date"))),
                 ("Main text", main_text), ("Topic", intro.get("topic") or s.get("main_theme")), ("Series", s.get("series"))],
        "overview": intro.get("overview") or s.get("summary") or "",
        "central_message": s.get("central_message") or s.get("main_theme") or "",
        "points": points,
        "sections": full_notes,
        "verses": verses,
        "explanations": explanations,
        "illustrations": illustrations,
        "quotes": [q for q in s.get("notable_quotes") or [] if isinstance(q, dict)],
        "applications": s.get("practical_applications") or [],
        "questions": s.get("study_questions") or [],
        "group": (s.get("sermon_start_info") or {}).get("small_group_guide") or {},
        "prayers": s.get("prayer_points") or [],
        "takeaways": takeaways,
        "conclusion": s.get("conclusion") or {},
    }


def sermon_markdown(s: dict) -> str:
    d = document_view(s)
    out = [f"# {(s.get('title') or 'Sermon').upper()}", "",
           f"*Sermon documentation{' · ' + _date(s.get('sermon_date')) if s.get('sermon_date') else ''}*", ""]

    out += ["## 1. Sermon information", "", "| Field | Detail |", "| --- | --- |"]
    out += [f"| {k} | {v} |" for k, v in d["info"] if v]
    if s.get("youtube_url"):
        out.append(f"| Video | {s['youtube_url']} |")
    out.append("")

    if d["overview"]:
        out += ["## 2. Sermon overview", "", d["overview"], ""]
    if d["central_message"]:
        out += ["## 3. Central message", "", f"> {d['central_message']}", ""]

    if d["points"]:
        out += ["## 4. Main teaching points", ""]
        for i, p in enumerate(d["points"], 1):
            line = f"**Point {i}: {p.get('point', '')}**{_t(p)}"
            out += [line, ""]
            if p.get("summary"):
                out += [p["summary"], ""]
        for i, sec in enumerate(d["sections"], 1):
            out += [f"### {sec.get('section_number') or i}. {sec.get('section_title', '')}{_t(sec)}", ""]
            if sec.get("full_teaching"):
                out += [sec["full_teaching"], ""]
            for v in sec.get("scriptures_in_this_section") or []:
                txt = f": \"{v['text_as_used']}\"" if v.get("text_as_used") else ""
                out.append(f"- **{v.get('reference', '')}**{txt}")
                if v.get("how_preacher_used_it"):
                    out.append(f"  - {v['how_preacher_used_it']}")
            if sec.get("scriptures_in_this_section"):
                out.append("")
            if sec.get("section_application"):
                out += [f"*Application:* {sec['section_application']}", ""]

    if d["verses"]:
        out += ["## 5. Scriptural references", "", "| Reference | Context | Relevance |", "| --- | --- | --- |"]
        for v in d["verses"]:
            ctx = (v.get("sermon_context") or "").replace("|", "/")
            rel = (v.get("relevance") or "").replace("|", "/")
            out.append(f"| {v.get('reference', '')}{_t(v)} | {ctx} | {rel} |")
        out.append("")

    if d["explanations"]:
        out += ["## 6. Important explanations and revelations", ""]
        for e in d["explanations"]:
            kind = f" *({e['kind']})*" if e.get("kind") else ""
            out += [f"**{e.get('title', '')}**{kind}{_t(e)}", "", e.get("explanation", "")]
            if e.get("scriptures"):
                out.append(f"*Scriptures:* {', '.join(e['scriptures'])}")
            out.append("")

    if d["illustrations"] or d["quotes"]:
        out += ["## 7. Illustrations and notable quotes", ""]
        for ill in d["illustrations"]:
            out += [f"**{ill.get('title', 'Illustration')}**", "", ill.get("full_story", "")]
            if ill.get("spiritual_point"):
                out += ["", f"*Point:* {ill['spiritual_point']}"]
            out.append("")
        for q in d["quotes"]:
            out += [f"> \"{q.get('quote', '')}\"{_t(q)}"]
            if q.get("context"):
                out.append(f"> *{q['context']}*")
            out.append("")

    if d["applications"]:
        out += ["## 8. Practical applications", ""]
        for a in d["applications"]:
            if isinstance(a, dict):
                out.append(f"- **{a.get('application', '')}**" + (f": {a['how_to_do_it']}" if a.get("how_to_do_it") else ""))
            else:
                out.append(f"- {a}")
        if s.get("weekly_challenge"):
            out += ["", f"**This week's challenge:** {s['weekly_challenge']}"]
        out.append("")

    if d["questions"] or d["group"]:
        out += ["## 9. Reflection and discussion questions", ""]
        for i, q in enumerate(d["questions"], 1):
            text = q.get("question", "") if isinstance(q, dict) else q
            tag = f" *({q['for']})*" if isinstance(q, dict) and q.get("for") in ("personal", "group") else ""
            out.append(f"{i}. {text}{tag}")
        g = d["group"] if isinstance(d["group"], dict) else {}
        if g.get("icebreaker") or g.get("discussion"):
            out += ["", "**For small groups**", ""]
            if g.get("icebreaker"):
                out.append(f"- Icebreaker: {g['icebreaker']}")
            for q in g.get("discussion") or []:
                out.append(f"- {q}")
            if g.get("activity"):
                out.append(f"- Activity: {g['activity']}")
        out.append("")

    if d["prayers"]:
        out += ["## 10. Prayer points", ""]
        for i, p in enumerate(d["prayers"], 1):
            text = p.get("point", "") if isinstance(p, dict) else p
            basis = f" ({p['scripture_basis']})" if isinstance(p, dict) and p.get("scripture_basis") else ""
            out.append(f"{i}. {text}{basis}")
        out.append("")

    if d["takeaways"]:
        out += ["## 11. Key takeaways", ""] + [f"- {t}" for t in d["takeaways"]] + [""]

    return "\n".join(out).strip() + "\n"
