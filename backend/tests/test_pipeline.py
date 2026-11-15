"""The full sermon pipeline and the API routes, with the network replaced by fakes."""
import pytest
from fastapi.testclient import TestClient

import main
from app import ai, jobs, transcripts
from app.auth import CurrentUser, get_current_user
from tests.fakes import FakeDB

USER = "11111111-1111-1111-1111-111111111111"

SEGMENTS = [{"text": "Welcome everyone, let's worship", "start": 0.0, "duration": 5.0}] + \
           [{"text": f"teaching sentence number {i} about faith and grace", "start": 600.0 + i * 6, "duration": 6.0}
            for i in range(300)]

NOTES = {
    "title": "Grace That Holds", "main_theme": "Grace keeps us", "summary": "S",
    "sermon_info": {"main_text": "Ephesians 2:8-9", "topic": "Grace", "series": "", "date_mentioned": ""},
    "overview": "An overview of grace.", "central_message": "Grace saves and keeps.",
    "main_points": [{"point": "Point one", "summary": "PS", "start_seconds": 610}],
    "explanations": [{"title": "Charis", "kind": "word study", "explanation": "Gift"}],
    "key_takeaways": ["Grace is a gift"],
    "introduction": {"opening": "O"}, "full_notes": [{"section_title": "Point one", "start_seconds": 610}],
    "all_bible_verses": [{"reference": "Ephesians 2:8"}], "related_topics": ["grace", "Faith"],
    "small_group_guide": {"icebreaker": "I"},
}


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(jobs, "user_db", lambda token: fake)
    monkeypatch.setattr(CurrentUser, "db", property(lambda self: fake))
    return fake


class FakeCalls(list):
    """Prompts sent to the AI (a list, for older assertions) plus the (provider, task, model) of each call."""
    def __init__(self):
        super().__init__()
        self.meta = []


@pytest.fixture
def fake_ai(monkeypatch):
    calls = FakeCalls()

    def fake_complete(prompt, system, choice, max_tokens, want_json, task="notes"):
        calls.append(prompt)
        model = ai.model_for(choice, task)
        calls.meta.append((choice, task, model))
        usage_obj = {"prompt_tokens": 10_000, "completion_tokens": 2_000, "prompt_tokens_details": {"cached_tokens": 4_000}}
        if "sermon_start_seconds" in prompt:
            text = '{"sermon_start_seconds": 600, "confidence": "high", "reason": "Turn your Bibles"}'
        elif "Return exactly this JSON structure" in prompt:
            import json
            text = json.dumps(NOTES)
        else:
            text = "Grace is God's gift [1]."
        return ai._Reply(text, False, model, usage_obj)
    monkeypatch.setattr(ai, "_complete", fake_complete)
    monkeypatch.setattr(ai.settings, "default_model", "openai")
    monkeypatch.setattr(ai.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(ai.settings, "embeddings_enabled", False)
    return calls


@pytest.fixture
def client(db):
    main.app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=USER, email="me@example.com", token="t")
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


@pytest.fixture
def sync_jobs(monkeypatch):
    """Run jobs inline instead of on the thread pool so tests can check the result."""
    monkeypatch.setattr(jobs, "submit", lambda token, uid, jid, inp, upload_path=None:
                        jobs.run_job(token, uid, jid, inp, upload_path))


def test_youtube_job_end_to_end(db, fake_ai, client, sync_jobs, monkeypatch):
    monkeypatch.setattr(transcripts, "video_details", lambda vid: {"title": "Sunday Service", "channel": "Grace Church"})
    monkeypatch.setattr(transcripts, "fetch_captions", lambda vid: SEGMENTS)

    r = client.post("/sermons/process", json={"url": "https://youtu.be/dQw4w9WgXcQ", "preacher": "Pastor Sam"})
    assert r.status_code == 200, r.text
    job_id = r.json()["job"]["id"]

    job = client.get(f"/jobs/{job_id}").json()
    assert job["status"] == "done", job
    assert job["progress"] == 100

    sermon = client.get(f"/sermons/{job['sermon_id']}").json()
    assert sermon["title"] == "Grace That Holds"
    assert sermon["church_name"] == "Grace Church"          # filled from the YouTube channel
    assert sermon["preacher"] == "Pastor Sam"
    assert sermon["sermon_start_seconds"] == 600
    assert sermon["topics"] == ["Grace", "Faith"]
    assert sermon["sermon_start_info"]["transcript_method"] == "captions"
    assert sermon["sermon_start_info"]["small_group_guide"] == {"icebreaker": "I"}
    assert sermon["timed_chunks"][0]["seconds"] == 600     # worship before the sermon is skipped
    assert "Welcome everyone" not in sermon["sermon_transcript"]

    chunks = db.tables["sermon_chunks"]
    assert chunks and all(c["sermon_id"] == sermon["id"] and c["user_id"] == USER for c in chunks)
    assert chunks[0]["start_seconds"] == 600

    # The same video again returns the existing sermon instead of paying for it twice
    again = client.post("/sermons/process", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}).json()
    assert again == {"job": None, "existing_sermon_id": sermon["id"]}


def test_whisper_fallback_when_captions_blocked(monkeypatch):
    class RequestBlocked(Exception):
        pass

    def blocked(vid):
        raise RequestBlocked("blocked")
    monkeypatch.setattr(transcripts, "fetch_captions", blocked)
    monkeypatch.setattr(transcripts, "download_audio", lambda vid, workdir: "/tmp/fake.m4a")
    monkeypatch.setattr(transcripts, "transcribe_audio", lambda path, progress=None: SEGMENTS)
    segs, method = transcripts.get_youtube_transcript("dQw4w9WgXcQ")
    assert method == "whisper" and segs == SEGMENTS


def test_clear_error_when_everything_is_blocked(monkeypatch):
    class RequestBlocked(Exception):
        pass

    def blocked(*a, **k):
        raise RequestBlocked("blocked")
    monkeypatch.setattr(transcripts, "fetch_captions", blocked)
    monkeypatch.setattr(transcripts, "download_audio", blocked)
    with pytest.raises(transcripts.TranscriptError) as err:
        transcripts.get_youtube_transcript("dQw4w9WgXcQ")
    msg = str(err.value)
    assert "blocked the caption request" in msg and "paste the transcript" in msg


def test_failed_job_records_error_and_can_retry(db, fake_ai, client, sync_jobs, monkeypatch):
    def boom(vid, progress=None):
        raise transcripts.TranscriptError("This video has no captions.")
    monkeypatch.setattr(transcripts, "video_details", lambda vid: {"title": "", "channel": ""})
    monkeypatch.setattr(transcripts, "get_youtube_transcript", boom)
    job_id = client.post("/sermons/process", json={"url": "dQw4w9WgXcQ"}).json()["job"]["id"]
    job = client.get(f"/jobs/{job_id}").json()
    assert job["status"] == "failed" and "no captions" in job["error"]

    monkeypatch.setattr(transcripts, "get_youtube_transcript", lambda vid, progress=None: (SEGMENTS, "captions"))
    assert client.post(f"/jobs/{job_id}/retry").status_code == 200
    assert client.get(f"/jobs/{job_id}").json()["status"] == "done"


def test_paste_job(db, fake_ai, client, sync_jobs):
    text = "\n".join(f"[{10 + i}:00] sentence {i} about prayer and faith in hard times" for i in range(40))
    job_id = client.post("/sermons/paste", json={"transcript_text": text, "title": "Pasted"}).json()["job"]["id"]
    job = client.get(f"/jobs/{job_id}").json()
    assert job["status"] == "done"
    sermon = client.get(f"/sermons/{job['sermon_id']}").json()
    assert sermon["source"] == "paste" and sermon["video_id"] is None


def test_ask_cites_sources(db, fake_ai, client, sync_jobs, monkeypatch):
    monkeypatch.setattr(transcripts, "video_details", lambda vid: {"title": "", "channel": "Grace Church"})
    monkeypatch.setattr(transcripts, "fetch_captions", lambda vid: SEGMENTS)
    client.post("/sermons/process", json={"url": "dQw4w9WgXcQ"})
    sermon_id = db.tables["sermons"][0]["id"]
    db.rpc_handlers["search_sermon_chunks"] = lambda p: [
        {"sermon_id": sermon_id, "chunk_index": 2, "start_seconds": 754, "content": "grace and faith", "score": 0.9}]

    r = client.post("/ask/", json={"question": "What did my pastor teach about grace?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answer"] == "Grace is God's gift [1]."
    src = body["sources"][0]
    assert src["n"] == 1 and src["title"] == "Grace That Holds" and src["time"] == "12:34"
    assert src["video_url"].endswith("v=dQw4w9WgXcQ&t=754s")
    assert "[1] \"Grace That Holds\"" in fake_ai[-1]       # the model saw the numbered excerpt


def test_list_topics_share_and_delete(db, fake_ai, client, sync_jobs, monkeypatch):
    monkeypatch.setattr(transcripts, "video_details", lambda vid: {"title": "", "channel": "Grace Church"})
    monkeypatch.setattr(transcripts, "fetch_captions", lambda vid: SEGMENTS)
    client.post("/sermons/process", json={"url": "dQw4w9WgXcQ"})
    sermon_id = db.tables["sermons"][0]["id"]

    assert len(client.get("/sermons/list").json()) == 1
    assert len(client.get("/sermons/list?topic=Grace").json()) == 1
    assert client.get("/sermons/list?topic=Marriage").json() == []
    idx = client.get("/sermons/topics").json()
    assert {"name": "Grace", "count": 1} in idx["topics"]
    assert {"name": "Ephesians", "count": 1} in idx["books"]
    assert client.get("/sermons/by-book/Ephesians").json()[0]["matching_verses"] == ["Ephesians 2:8"]

    assert client.patch(f"/sermons/{sermon_id}", json={"is_public": True}).json()["is_public"] is True
    md = client.get(f"/sermons/{sermon_id}/markdown").json()
    assert md["filename"] == "grace-that-holds.md" and md["markdown"].startswith("# GRACE THAT HOLDS")

    assert client.delete(f"/sermons/{sermon_id}").status_code == 200
    assert client.get(f"/sermons/{sermon_id}").status_code == 404


def test_other_users_rows_are_not_listed(db, client):
    db.tables["sermons"] = [{"id": "x", "user_id": "someone-else", "title": "Not mine", "is_public": True,
                             "created_at": "2026-01-01"}]
    assert client.get("/sermons/list").json() == []
    assert client.get("/sermons/x").status_code == 404


def test_requires_sign_in():
    main.app.dependency_overrides.clear()
    c = TestClient(main.app)
    assert c.get("/sermons/list").status_code == 401
    assert c.get("/health").json() == {"status": "ok"}
    cfg = c.get("/config").json()
    assert {m["id"] for m in cfg["models"]} == {"claude", "groq"}
    assert cfg["semantic_search"] is False


def test_monthly_limit(db, client, monkeypatch):
    monkeypatch.setattr(main.settings, "monthly_sermon_limit", 1)
    monkeypatch.setattr(jobs, "submit", lambda *a, **k: None)
    assert client.post("/sermons/process", json={"url": "dQw4w9WgXcQ"}).status_code == 200
    r = client.post("/sermons/process", json={"url": "https://youtu.be/aaaaaaaaaaa"})
    assert r.status_code == 429


def test_stale_jobs_marked_failed(db):
    db.tables["jobs"] = [{"id": "j1", "status": "running", "updated_at": "2020-01-01T00:00:00+00:00"}]
    out = jobs.mark_stale(db, [dict(db.tables["jobs"][0])])
    assert out[0]["status"] == "failed" and db.tables["jobs"][0]["status"] == "failed"


def test_new_sermon_gets_documentation_fields(db, fake_ai, client, sync_jobs, monkeypatch):
    monkeypatch.setattr(transcripts, "video_details", lambda vid: {"title": "", "channel": "Grace Church"})
    monkeypatch.setattr(transcripts, "fetch_captions", lambda vid: SEGMENTS)
    r = client.post("/sermons/process", json={"url": "dQw4w9WgXcQ", "series": "Foundations", "sermon_date": "2026-11-15"})
    assert r.status_code == 200, r.text
    s = db.tables["sermons"][0]
    assert s["central_message"] == "Grace saves and keeps."
    assert s["main_text"] == "Ephesians 2:8-9" and s["series"] == "Foundations" and s["sermon_date"] == "2026-11-15"
    assert s["main_points"][0]["point"] == "Point one" and s["key_takeaways"] == ["Grace is a gift"]
    assert s["introduction"]["overview"] == "An overview of grace."
    assert s["curation_version"] == 2
    # what the user typed is passed to the AI as trusted context
    assert "- Series: Foundations" in fake_ai[-1] and "- Date preached: 2026-11-15" in fake_ai[-1]


def test_bad_date_rejected(db, client):
    r = client.post("/sermons/process", json={"url": "dQw4w9WgXcQ", "sermon_date": "next sunday"})
    assert r.status_code == 400


def test_recurate_rewrites_from_saved_transcript(db, fake_ai, client, sync_jobs):
    db.tables["sermons"] = [{"id": "s1", "user_id": USER, "title": "Old title", "preacher": "Pastor Sam",
                             "series": "Kept series", "sermon_date": "2026-10-01", "is_public": True,
                             "timed_chunks": [{"seconds": 600 + i * 60, "time": "", "text": f"teaching about grace {i} " * 5}
                                              for i in range(20)],
                             "sermon_start_info": {"sermon_start_time": "10:00"}, "created_at": "2026-10-01"}]
    job_id = client.post("/sermons/s1/recurate", json={}).json()["job"]["id"]
    assert client.get(f"/jobs/{job_id}").json()["status"] == "done"
    s = db.tables["sermons"][0]
    assert s["title"] == "Grace That Holds" and s["central_message"] == "Grace saves and keeps."
    assert s["series"] == "Kept series" and s["sermon_date"] == "2026-10-01" and s["is_public"] is True
    assert s["sermon_start_info"]["sermon_start_time"] == "10:00"
    assert "[10:00] teaching about grace 0" in fake_ai[-1]
    assert client.post("/sermons/nope/recurate", json={}).status_code == 404


def test_library_search_finds_words_said_in_transcript(db, client):
    db.tables["sermons"] = [{"id": "s1", "user_id": USER, "title": "Walking in Love", "summary": "", "created_at": "2026-11-01"}]
    db.rpc_handlers["search_sermon_chunks"] = lambda p: [
        {"sermon_id": "s1", "chunk_index": 3, "start_seconds": 1265, "content": "and the pastor said the mustard seed grows quietly", "score": 1}]
    rows = client.get("/sermons/list?q=mustard seed").json()
    assert rows[0]["id"] == "s1"
    assert rows[0]["transcript_match"]["time"] == "21:05"
    assert "mustard seed" in rows[0]["transcript_match"]["excerpt"]


def test_each_task_uses_its_tier_and_costs_are_recorded(db, fake_ai, client, sync_jobs, monkeypatch):
    monkeypatch.setattr(transcripts, "video_details", lambda vid: {"title": "", "channel": "Grace Church"})
    monkeypatch.setattr(transcripts, "fetch_captions", lambda vid: SEGMENTS)
    job_id = client.post("/sermons/process", json={"url": "dQw4w9WgXcQ"}).json()["job"]["id"]
    assert client.get(f"/jobs/{job_id}").json()["status"] == "done"
    assert ("openai", "start", "gpt-5.4-nano") in fake_ai.meta
    assert ("openai", "notes", "gpt-5.4") in fake_ai.meta

    rows = db.tables["ai_usage"]
    by_task = {r["task"]: r for r in rows}
    assert by_task["notes"]["model"] == "gpt-5.4" and by_task["start"]["model"] == "gpt-5.4-nano"
    assert all(r["job_id"] == job_id and r["user_id"] == USER for r in rows)
    sermon = db.tables["sermons"][0]
    assert all(r["sermon_id"] == sermon["id"] for r in rows)
    # gpt-5.4: 6,000 uncached x $2.50 + 4,000 cached x $0.25 + 2,000 out x $15, per 1M tokens
    assert by_task["notes"]["cost_usd"] == pytest.approx(0.046)
    # gpt-5.4-nano: 6,000 x $0.20 + 4,000 x $0.02 + 2,000 x $1.25
    assert by_task["start"]["cost_usd"] == pytest.approx(0.00378)
    assert float(sermon["cost_usd"]) == pytest.approx(0.04978)
    assert sermon["models_used"] == {"start": "gpt-5.4-nano", "notes": "gpt-5.4"}
    assert sermon["model_used"] == "gpt-5.4"
    job = db.tables["jobs"][0]
    assert float(job["cost_usd"]) == pytest.approx(0.04978)


def test_premium_uses_premium_model(db, fake_ai, client, sync_jobs, monkeypatch):
    monkeypatch.setattr(transcripts, "video_details", lambda vid: {"title": "", "channel": ""})
    monkeypatch.setattr(transcripts, "fetch_captions", lambda vid: SEGMENTS)
    client.post("/sermons/process", json={"url": "dQw4w9WgXcQ", "premium": True})
    assert ("openai", "notes_premium", "gpt-5.5") in fake_ai.meta
    assert db.tables["sermons"][0]["model_used"] == "gpt-5.5"


def test_ask_uses_fast_tier_and_reports_cost(db, fake_ai, client):
    db.tables["sermons"] = [{"id": "s1", "user_id": USER, "title": "T", "created_at": "2026-11-01"}]
    db.rpc_handlers["search_sermon_chunks"] = lambda p: [
        {"sermon_id": "s1", "chunk_index": 0, "start_seconds": 60, "content": "grace", "score": 1}]
    body = client.post("/ask/", json={"question": "What is grace?"}).json()
    assert body["model_used"] == "gpt-5.4-mini"
    # 6,000 x $0.75 + 4,000 x $0.075 + 2,000 x $4.50, per 1M
    assert body["cost_usd"] == pytest.approx(0.0138)
    assert db.tables["ai_usage"][0]["task"] == "ask" and db.tables["ai_usage"][0]["sermon_id"] is None


def test_failed_job_still_records_spend(db, fake_ai, client, sync_jobs, monkeypatch):
    monkeypatch.setattr(transcripts, "video_details", lambda vid: {"title": "", "channel": ""})
    monkeypatch.setattr(transcripts, "fetch_captions", lambda vid: SEGMENTS)
    from app import notes as notes_mod

    def boom(*a, **k):
        ai.complete("x", "y", None, task="notes")  # spends money, then fails
        raise ai.AIError("The AI reply was not valid JSON.")
    monkeypatch.setattr(notes_mod, "write_notes", boom)
    job_id = client.post("/sermons/process", json={"url": "dQw4w9WgXcQ"}).json()["job"]["id"]
    job = client.get(f"/jobs/{job_id}").json()
    assert job["status"] == "failed"
    assert len(db.tables["ai_usage"]) == 2  # start detection + the failed notes call
    assert float(db.tables["jobs"][0]["cost_usd"]) > 0


def test_usage_summary(db, client):
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    db.tables["sermons"] = [{"id": "s1", "user_id": USER, "title": "Grace", "cost_usd": 0.3,
                             "models_used": {"notes": "gpt-5.4"}, "created_at": now.isoformat()}]
    db.tables["ai_usage"] = [
        {"user_id": USER, "created_at": now.isoformat(), "task": "notes", "provider": "openai", "model": "gpt-5.4",
         "input_tokens": 15000, "output_tokens": 12000, "cost_usd": 0.28, "sermon_id": "s1"},
        {"user_id": USER, "created_at": now.isoformat(), "task": "start", "provider": "openai", "model": "gpt-5.4-nano",
         "input_tokens": 4000, "output_tokens": 100, "cost_usd": 0.001, "sermon_id": "s1"},
        {"user_id": USER, "created_at": now.isoformat(), "task": "ask", "provider": "openai", "model": "gpt-5.4-mini",
         "input_tokens": 3000, "output_tokens": 800, "cost_usd": 0.006, "sermon_id": None},
        {"user_id": "someone-else", "created_at": now.isoformat(), "task": "ask", "provider": "openai",
         "model": "gpt-5.5", "cost_usd": 9.0, "sermon_id": None},
        {"user_id": USER, "created_at": (now - timedelta(days=400)).isoformat(), "task": "ask", "provider": "openai",
         "model": "gpt-5.5", "cost_usd": 5.0, "sermon_id": None},
    ]
    u = client.get("/usage").json()
    assert u["window_total"] == pytest.approx(0.287) and u["calls"] == 3
    assert u["by_task"][0] == {"task": "notes", "label": "Sermon documents", "cost": 0.28, "calls": 1}
    assert [m["model"] for m in u["by_model"]] == ["gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano"]
    assert u["avg_cost_per_sermon"] == pytest.approx(0.281)
    assert u["recent_sermons"][0]["title"] == "Grace"


def test_config_reports_model_per_job(client, monkeypatch):
    monkeypatch.setattr(main.settings, "openai_api_key", "k")
    cfg = client.get("/config").json()
    openai_cfg = next(m for m in cfg["models"] if m["id"] == "openai")
    assert openai_cfg["tiers"] == {"notes": "gpt-5.4", "notes_premium": "gpt-5.5", "ask": "gpt-5.4-mini",
                                   "verse": "gpt-5.4-mini", "guide": "gpt-5.4", "start": "gpt-5.4-nano"}
