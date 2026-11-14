import pytest

from app import ai, notes, transcripts
from app.exporting import sermon_markdown


@pytest.mark.parametrize("url,expected", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ?t=42", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/live/dQw4w9WgXcQ?si=abc", "dQw4w9WgXcQ"),
    ("https://youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL123", "dQw4w9WgXcQ"),
    ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://example.com/video", None),
])
def test_extract_video_id(url, expected):
    assert transcripts.extract_video_id(url) == expected


def test_playlist_id():
    assert transcripts.extract_playlist_id("https://youtube.com/playlist?list=PLabc_123") == "PLabc_123"
    assert transcripts.extract_playlist_id("https://youtube.com/watch?v=x") is None


@pytest.mark.parametrize("value,expected", [("14:32", 872), ("1:02:03", 3723), ("870", 870), (90, 90),
                                            ("", None), (None, None), ("abc", None)])
def test_parse_time(value, expected):
    assert transcripts.parse_time(value) == expected


def test_format_time():
    assert transcripts.format_time(75) == "1:15"
    assert transcripts.format_time(3723) == "1:02:03"


def test_pasted_text_keeps_timestamps():
    text = "[0:05] Good morning church\n12:30 Turn with me to John 3\n[1:02:03] Let us pray\n13:00 - God so loved"
    segs = transcripts.segments_from_text(text)
    assert [s["start"] for s in segs] == [5, 750, 3723, 780]
    assert segs[1]["text"] == "Turn with me to John 3"


def test_pasted_text_without_timestamps_gets_rough_times():
    text = " ".join(["word"] * 400)
    segs = transcripts.segments_from_text(text)
    assert len(segs) == 10
    assert segs[0]["start"] == 0
    assert segs[-1]["start"] == pytest.approx(360 / 150 * 60)


def test_pasted_empty_raises():
    with pytest.raises(transcripts.TranscriptError):
        transcripts.segments_from_text("   \n  ")


def _segs(n=200, step=5):
    return [{"text": f"line {i}", "start": float(i * step), "duration": float(step)} for i in range(n)]


def test_timed_lines_and_chunks_start_at_sermon_start():
    segs = _segs()
    lines = notes.timed_lines(segs, start_seconds=300, every=30).splitlines()
    assert lines[0].startswith("[5:00] line 60")
    chunks = notes.build_timed_chunks(segs, start_seconds=300)
    assert chunks[0]["seconds"] == 300 and chunks[0]["time"] == "5:00"
    assert all(c["seconds"] >= 300 for c in chunks)
    assert len(chunks) == (1000 - 300) // 60 + 1


def test_search_chunks_cover_everything_after_start():
    segs = _segs()
    chunks = notes.search_chunks(segs, start_seconds=100, target_chars=100)
    joined = " ".join(c["content"] for c in chunks)
    assert "line 19 " not in joined + " "
    assert joined.startswith("line 20")
    assert joined.endswith("line 199")
    assert chunks[0]["start_seconds"] == 100


def test_clean_topics():
    assert notes.clean_topics({"related_topics": ["faith", "Faith ", "holy  spirit", "", 3, "x" * 60]}) == \
        ["Faith", "Holy spirit"]


@pytest.mark.parametrize("ref,book", [("John 3:16", "John"), ("1 Corinthians 13:4-7", "1 Corinthians"),
                                      ("Song of Solomon 2:4", "Song Of Solomon"), ("nonsense", None)])
def test_verse_book(ref, book):
    assert notes.verse_book(ref) == book


def test_parse_json_variants():
    assert ai.parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert ai.parse_json('Here you go: {"a": [1, 2]}') == {"a": [1, 2]}
    truncated = '{"title": "Faith", "full_notes": [{"section_title": "One", "full_teaching": "God is'
    out = ai.parse_json(truncated)
    assert out["title"] == "Faith" and out["full_notes"][0]["section_title"] == "One"
    with pytest.raises(ai.AIError):
        ai.parse_json("no json here")


def test_resolve_model_falls_back_to_available(monkeypatch):
    monkeypatch.setattr(ai.settings, "anthropic_api_key", "")
    monkeypatch.setattr(ai.settings, "openai_api_key", "")
    monkeypatch.setattr(ai.settings, "groq_api_key", "k")
    assert ai.resolve_model("claude") == "groq"
    monkeypatch.setattr(ai.settings, "groq_api_key", "")
    with pytest.raises(ai.AIError):
        ai.resolve_model("claude")


def test_markdown_export_follows_documentation_structure():
    md = sermon_markdown({
        "title": "The Power of Spiritual Understanding", "preacher": "Pastor Sam", "church_name": "Grace Church",
        "sermon_date": "2026-11-15", "series": "Spiritual Growth", "main_text": "Ephesians 1:17-18",
        "introduction": {"overview": "An overview.", "topic": "Spiritual understanding"},
        "central_message": "Understanding is given by the Spirit.",
        "main_points": [{"point": "Understanding God's Word", "summary": "S1", "start_seconds": 750}],
        "full_notes": [{"section_number": 1, "section_title": "Understanding God's Word", "start_seconds": 750,
                        "full_teaching": "Body", "illustrations": [{"title": "The lamp", "full_story": "Story"}]}],
        "all_bible_verses": [{"reference": "Ephesians 1:17", "sermon_context": "Paul's prayer", "relevance": "Source", "start_seconds": 760}],
        "explanations": [{"title": "Epignosis", "kind": "word study", "explanation": "Full knowledge"}],
        "notable_quotes": [{"quote": "Light comes before sight."}],
        "practical_applications": [{"application": "Pray Ephesians 1 daily"}],
        "study_questions": [{"question": "Where do you need light?", "for": "personal"}],
        "prayer_points": [{"point": "Father, open my eyes", "scripture_basis": "Ephesians 1:18"}],
        "key_takeaways": ["Understanding is a gift"],
    })
    assert md.startswith("# THE POWER OF SPIRITUAL UNDERSTANDING")
    assert "Sermon documentation · 15 November 2026" in md
    for n, title in enumerate(["Sermon information", "Sermon overview", "Central message", "Main teaching points",
                               "Scriptural references", "Important explanations and revelations",
                               "Illustrations and notable quotes", "Practical applications",
                               "Reflection and discussion questions", "Prayer points", "Key takeaways"], 1):
        assert f"## {n}. {title}" in md
    assert "| Main text | Ephesians 1:17-18 |" in md and "| Series | Spiritual Growth |" in md
    assert "**Point 1: Understanding God's Word** (12:30)" in md
    assert "| Ephesians 1:17 (12:40) | Paul's prayer | Source |" in md
    assert "**Epignosis** *(word study)*" in md
    assert "1. Father, open my eyes (Ephesians 1:18)" in md


def test_markdown_export_handles_older_sermons():
    md = sermon_markdown({"title": "Old", "main_theme": "Grace", "summary": "Short",
                          "full_notes": [{"section_title": "First point"}],
                          "theological_depths": [{"concept": "Grace", "full_explanation": "Unmerited favour"}]})
    assert "## 3. Central message" in md and "> Grace" in md
    assert "**Point 1: First point**" in md
    assert "**Grace**" in md and "## 11. Key takeaways" in md


def test_document_fields_mapping():
    from app.notes import document_fields
    doc = document_fields({"sermon_info": {"main_text": "John 3:16", "series": "Love", "date_mentioned": "15 Nov"},
                           "central_message": "God loves", "explanations": [{"title": "Agape", "explanation": "E"}],
                           "key_takeaways": ["One", "", "Two"], "full_notes": [{"section_title": "A", "start_seconds": 5}]})
    assert doc["main_text"] == "John 3:16" and doc["series_hint"] == "Love"
    assert doc["date_hint"] is None                      # only ISO dates are trusted
    assert doc["main_points"] == [{"point": "A", "summary": "", "start_seconds": 5}]
    assert doc["theological_depths"] == [{"concept": "Agape", "full_explanation": "E"}]
    assert doc["key_takeaways"] == ["One", "Two"]


def test_prompt_includes_known_details():
    from app.notes import notes_prompt
    p = notes_prompt("[0:00] hello", {"Preacher": "Pastor Sam", "Series": ""})
    assert "- Preacher: Pastor Sam" in p and "Series:" not in p
    assert "Curate this sermon transcript" in p and '"key_takeaways"' in p

class _FakeCompletions:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class _FakeClient:
    def __init__(self, replies):
        self.chat = type("Chat", (), {})()
        self.chat.completions = _FakeCompletions(replies)


def _resp(text, finish="stop"):
    msg = type("M", (), {"content": text})()
    choice = type("C", (), {"message": msg, "finish_reason": finish})()
    return type("R", (), {"choices": [choice]})()


def test_chat_drops_parameters_the_model_rejects():
    client = _FakeClient([Exception("Unsupported parameter: 'reasoning_effort' is not supported with this model."),
                          _resp('{"ok": true}')])
    out = ai._chat(client, {"model": "m", "messages": []}, {"reasoning_effort": "low", "response_format": {"type": "json_object"}})
    assert out.choices[0].message.content == '{"ok": true}'
    assert "reasoning_effort" in client.chat.completions.calls[0]
    assert "reasoning_effort" not in client.chat.completions.calls[1]
    assert "response_format" in client.chat.completions.calls[1]


def test_chat_reraises_unrelated_errors():
    client = _FakeClient([Exception("Incorrect API key provided")])
    with pytest.raises(Exception, match="Incorrect API key"):
        ai._chat(client, {"model": "m"}, {"reasoning_effort": "low"})


def test_complete_json_retries_empty_and_broken_replies(monkeypatch):
    replies = [ai._Reply("", True), ai._Reply("not json at all", False), ai._Reply('{"title": "Ok"}', False)]
    monkeypatch.setattr(ai, "_complete", lambda *a, **k: replies.pop(0))
    with pytest.raises(ai.AIError, match="not valid JSON"):
        ai.complete_json("p", "s", "groq")            # two attempts: empty, then broken
    assert ai.complete_json("p", "s", "groq") == {"title": "Ok"}


def test_complete_json_does_not_retry_auth_errors(monkeypatch):
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise RuntimeError("invalid x-api-key")
    monkeypatch.setattr(ai, "_complete", boom)
    with pytest.raises(ai.AIError, match="request failed"):
        ai.complete_json("p", "s", "groq")
    assert len(calls) == 1


def test_openai_gets_reasoning_headroom(monkeypatch):
    fake = _FakeClient([_resp('{"a": 1}')])
    import openai
    monkeypatch.setattr(openai, "OpenAI", lambda **k: fake)
    monkeypatch.setattr(ai.settings, "openai_api_key", "k")
    assert ai.complete_json("p", "s", "openai", max_tokens=16000) == {"a": 1}
    call = fake.chat.completions.calls[0]
    assert call["max_completion_tokens"] == 48000 and call["reasoning_effort"] == "low"
