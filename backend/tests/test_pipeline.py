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


@pytest.fixture
def fake_ai(monkeypatch):
    calls = []

    def complete(prompt, system, model_choice=None, max_tokens=4096, want_json=False):
        calls.append(prompt)
        if "sermon_start_seconds" in prompt:
            return '{"sermon_start_seconds": 600, "confidence": "high", "reason": "Turn your Bibles"}'
        if "Return exactly this JSON structure" in prompt:
            import json
            return json.dumps(NOTES)
        return "Grace is God's gift [1]."
    monkeypatch.setattr(ai, "complete", complete)
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
    assert md["filename"] == "grace-that-holds.md" and md["markdown"].startswith("# Grace That Holds")

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
