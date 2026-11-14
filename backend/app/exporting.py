"""Sermon notes as Markdown, for download or pasting into WhatsApp, Notion, Google Docs."""
from .transcripts import format_time


def _list(items, fmt):
    return "\n".join(fmt(i) for i in items or [] if i)


def _t(item: dict, key: str = "start_seconds") -> str:
    s = item.get(key) if isinstance(item, dict) else None
    return f" ({format_time(s)})" if isinstance(s, (int, float)) and s > 0 else ""


def sermon_markdown(s: dict) -> str:
    out = [f"# {s.get('title') or 'Sermon'}", ""]
    meta = " · ".join(x for x in [s.get("preacher"), s.get("church_name")] if x)
    if meta:
        out += [f"*{meta}*", ""]
    if s.get("youtube_url"):
        out += [f"Video: {s['youtube_url']}", ""]
    if s.get("main_theme"):
        out += [f"**Main theme:** {s['main_theme']}", ""]
    if s.get("summary"):
        out += ["## Summary", "", s["summary"], ""]

    intro = s.get("introduction") or {}
    if any(intro.values()):
        out += ["## Introduction", ""]
        for key, label in (("opening", "Opening"), ("context", "Context"), ("thesis", "Thesis")):
            if intro.get(key):
                out += [f"**{label}:** {intro[key]}", ""]

    for i, sec in enumerate(s.get("full_notes") or [], 1):
        out += [f"## {sec.get('section_number') or i}. {sec.get('section_title', '')}{_t(sec)}", ""]
        if sec.get("full_teaching"):
            out += [sec["full_teaching"], ""]
        for ill in sec.get("illustrations") or []:
            out += [f"> **Illustration: {ill.get('title', '')}**  ", f"> {ill.get('full_story', '')}"]
            if ill.get("spiritual_point"):
                out += [f">  ", f"> *Point:* {ill['spiritual_point']}"]
            out.append("")
        for v in sec.get("scriptures_in_this_section") or []:
            line = f"- **{v.get('reference', '')}**"
            if v.get("text_as_used"):
                line += f": \"{v['text_as_used']}\""
            out.append(line)
            if v.get("how_preacher_used_it"):
                out.append(f"  - {v['how_preacher_used_it']}")
        if sec.get("scriptures_in_this_section"):
            out.append("")
        for q in sec.get("key_statements") or []:
            out += [f"> \"{q}\"", ""]
        if sec.get("section_application"):
            out += [f"**Application:** {sec['section_application']}", ""]

    concl = s.get("conclusion") or {}
    if any(concl.values()):
        out += ["## Conclusion", ""]
        for key, label in (("closing_argument", "Closing"), ("call_to_action", "Call to action"),
                           ("closing_prayer_or_charge", "Charge")):
            if concl.get(key):
                out += [f"**{label}:** {concl[key]}", ""]

    verses = s.get("all_bible_verses") or []
    if verses:
        out += ["## Bible verses", "", _list(verses, lambda v: f"- **{v.get('reference', '')}**{_t(v)}"
                                             + (f": {v['sermon_context']}" if v.get("sermon_context") else "")), ""]
    apps = s.get("practical_applications") or []
    if apps:
        out += ["## Practical applications", "",
                _list(apps, lambda a: f"- **{a.get('application', a) if isinstance(a, dict) else a}**"
                      + (f": {a.get('how_to_do_it')}" if isinstance(a, dict) and a.get("how_to_do_it") else "")), ""]
    prayers = s.get("prayer_points") or []
    if prayers:
        out += ["## Prayer points", "",
                _list(prayers, lambda p: f"- {p.get('point', '') if isinstance(p, dict) else p}"
                      + (f" ({p['scripture_basis']})" if isinstance(p, dict) and p.get("scripture_basis") else "")), ""]
    qs = s.get("study_questions") or []
    if qs:
        out += ["## Study questions", "",
                "\n".join(f"{i}. {q.get('question', '') if isinstance(q, dict) else q}" for i, q in enumerate(qs, 1)), ""]
    guide = (s.get("sermon_start_info") or {}).get("small_group_guide") or {}
    if any(guide.values()) if isinstance(guide, dict) else False:
        out += ["## Small group guide", ""]
        if guide.get("icebreaker"):
            out += [f"**Icebreaker:** {guide['icebreaker']}", ""]
        if guide.get("discussion"):
            out += ["\n".join(f"{i}. {q}" for i, q in enumerate(guide["discussion"], 1)), ""]
        if guide.get("activity"):
            out += [f"**Activity:** {guide['activity']}", ""]
        if guide.get("closing_prayer"):
            out += [f"**Closing prayer:** {guide['closing_prayer']}", ""]
    if s.get("weekly_challenge"):
        out += ["## This week's challenge", "", s["weekly_challenge"], ""]
    if s.get("topics"):
        out += [f"*Topics: {', '.join(s['topics'])}*", ""]
    return "\n".join(out).strip() + "\n"
