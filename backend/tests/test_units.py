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


def test_markdown_export_has_sections():
    md = sermon_markdown({
        "title": "Walking by Faith", "preacher": "Pastor Sam", "church_name": "Grace Church",
        "summary": "A message on trust.", "main_theme": "Trust God",
        "full_notes": [{"section_number": 1, "section_title": "Faith sees", "start_seconds": 750,
                        "full_teaching": "Body", "scriptures_in_this_section": [{"reference": "Hebrews 11:1"}]}],
        "all_bible_verses": [{"reference": "Hebrews 11:1", "start_seconds": 760}],
        "study_questions": [{"question": "What does faith mean to you?"}],
        "sermon_start_info": {"small_group_guide": {"icebreaker": "Hi", "discussion": ["Q1"]}},
        "topics": ["Faith"],
    })
    assert md.startswith("# Walking by Faith")
    assert "## 1. Faith sees (12:30)" in md
    assert "**Hebrews 11:1** (12:40)" in md
    assert "## Small group guide" in md and "1. What does faith mean to you?" in md
