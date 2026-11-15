"""Getting a sermon's words, with timestamps.

Order of attempts for a YouTube link:
  1. YouTube captions (fast, free) - often blocked from cloud servers, so a proxy can be set.
  2. Download the audio with yt-dlp and transcribe it with Whisper (Groq or OpenAI).
Users can also upload an audio/video file, or paste a transcript, which skips YouTube entirely.
"""
import glob
import logging
import os
import re
import shutil
import subprocess
import tempfile
from typing import Callable, Optional

import httpx

from .config import settings

log = logging.getLogger("transcripts")

Segment = dict  # {"text": str, "start": float, "duration": float}
Progress = Callable[[str, int], None]


class TranscriptError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------
_VIDEO_ID = re.compile(r"(?:v=|youtu\.be/|embed/|shorts/|live/|/v/)([a-zA-Z0-9_-]{11})")
_PLAYLIST_ID = re.compile(r"[?&]list=([a-zA-Z0-9_-]+)")


def extract_video_id(url: str) -> Optional[str]:
    url = (url or "").strip()
    if re.fullmatch(r"[a-zA-Z0-9_-]{11}", url):
        return url
    m = _VIDEO_ID.search(url)
    return m.group(1) if m else None


def extract_playlist_id(url: str) -> Optional[str]:
    m = _PLAYLIST_ID.search(url or "")
    return m.group(1) if m else None


def format_time(seconds: float) -> str:
    m, s = divmod(int(seconds or 0), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def parse_time(value) -> Optional[int]:
    """'14:32', '1:02:03' or '870' -> seconds."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    try:
        parts = [int(p) for p in text.split(":")]
    except ValueError:
        return None
    total = 0
    for p in parts:
        total = total * 60 + p
    return total


# ---------------------------------------------------------------------------
# Video details (title, channel) without hitting the blocked endpoints
# ---------------------------------------------------------------------------
def video_details(video_id: str) -> dict:
    try:
        resp = httpx.get(
            "https://www.youtube.com/oembed",
            params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            return {"title": data.get("title", ""), "channel": data.get("author_name", "")}
    except httpx.HTTPError:
        pass
    return {"title": "", "channel": ""}


# ---------------------------------------------------------------------------
# 1. Captions
# ---------------------------------------------------------------------------
def _caption_proxy():
    from youtube_transcript_api.proxies import GenericProxyConfig, WebshareProxyConfig
    if settings.webshare_username and settings.webshare_password:
        return WebshareProxyConfig(proxy_username=settings.webshare_username,
                                   proxy_password=settings.webshare_password)
    if settings.yt_proxy_url:
        return GenericProxyConfig(http_url=settings.yt_proxy_url, https_url=settings.yt_proxy_url)
    return None


def fetch_captions(video_id: str) -> list[Segment]:
    from youtube_transcript_api import YouTubeTranscriptApi
    api = YouTubeTranscriptApi(proxy_config=_caption_proxy())
    listing = api.list(video_id)
    try:
        transcript = listing.find_transcript(settings.transcript_languages)
    except Exception:
        transcript = next(iter(listing), None)  # any language; the notes are written in English
        if transcript is None:
            raise TranscriptError("This video has no captions.")
    fetched = transcript.fetch()
    segments = [{"text": s.text.replace("\n", " ").strip(), "start": float(s.start), "duration": float(s.duration)}
                for s in fetched if s.text and s.text.strip()]
    if not segments:
        raise TranscriptError("The captions for this video are empty.")
    return segments


# ---------------------------------------------------------------------------
# 2. Audio + Whisper
# ---------------------------------------------------------------------------
def _ytdlp_opts(extra: dict) -> dict:
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True}
    if settings.yt_proxy_url:
        opts["proxy"] = settings.yt_proxy_url
    if settings.ytdlp_cookies_file and os.path.exists(settings.ytdlp_cookies_file):
        opts["cookiefile"] = settings.ytdlp_cookies_file
    opts.update(extra)
    return opts


def download_audio(video_id: str, workdir: str) -> str:
    import yt_dlp
    out = os.path.join(workdir, "source.%(ext)s")
    opts = _ytdlp_opts({"format": "bestaudio/best", "outtmpl": out})
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
    files = glob.glob(os.path.join(workdir, "source.*"))
    if not files:
        raise TranscriptError("Could not download the audio for this video.")
    return files[0]


def _whisper_ready() -> bool:
    if settings.whisper_provider == "openai":
        return bool(settings.openai_api_key)
    return bool(settings.groq_api_key or settings.openai_api_key)


def split_audio(path: str, workdir: str, chunk_seconds: int = 600) -> list[tuple[str, float]]:
    """Re-encode to small mono MP3 pieces (about 2.4 MB per 10 minutes), safe for Whisper size limits."""
    if not shutil.which("ffmpeg"):
        raise TranscriptError("ffmpeg is not installed on the server, so audio cannot be transcribed.")
    pattern = os.path.join(workdir, "part_%03d.mp3")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-vn", "-ac", "1", "-ar", "16000",
           "-b:a", "32k", "-f", "segment", "-segment_time", str(chunk_seconds), "-reset_timestamps", "1", pattern]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if result.returncode != 0:
        raise TranscriptError(f"Could not read the audio file: {result.stderr.strip()[:300]}")
    parts = sorted(glob.glob(os.path.join(workdir, "part_*.mp3")))
    if not parts:
        raise TranscriptError("The audio file appears to be empty.")
    return [(p, i * chunk_seconds) for i, p in enumerate(parts)]


def _seg_get(seg, key, default=None):
    return seg.get(key, default) if isinstance(seg, dict) else getattr(seg, key, default)


def _use_groq_audio() -> bool:
    return bool(settings.whisper_provider != "openai" and settings.groq_api_key)


def _part_seconds(path: str) -> float:
    """Length of an ffmpeg part: we encode at a constant 32 kbit/s, so size tells us the duration."""
    try:
        return round(os.path.getsize(path) * 8 / 32000, 1)
    except OSError:
        return 0.0


def _spread(text: str, offset: float, length: float) -> list[Segment]:
    """When a model returns plain text without times, spread its sentences evenly across the part."""
    sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+", text or "") if x.strip()]
    if not sentences:
        return []
    total = sum(len(x) for x in sentences) or 1
    out, pos = [], 0
    for x in sentences:
        out.append({"text": x, "start": offset + length * pos / total, "duration": length * len(x) / total})
        pos += len(x)
    return out


def _openai_transcribe(fh, model: str):
    """Ask for segment timestamps; models that only return plain text get a plain request instead."""
    from openai import OpenAI
    client = OpenAI(api_key=settings.openai_api_key, max_retries=3, timeout=600)
    try:
        return client.audio.transcriptions.create(file=fh, model=model, response_format="verbose_json",
                                                  timestamp_granularities=["segment"]), True
    except Exception as e:
        msg = str(e).lower()
        if "response_format" not in msg and "timestamp" not in msg and "verbose" not in msg:
            raise
        fh.seek(0)
        return client.audio.transcriptions.create(file=fh, model=model, response_format="json"), False


def transcribe_file(path: str, offset: float) -> list[Segment]:
    from . import usage
    length = _part_seconds(path)
    with open(path, "rb") as fh:
        if _use_groq_audio():
            from groq import Groq
            client = Groq(api_key=settings.groq_api_key, max_retries=3, timeout=600)
            resp = client.audio.transcriptions.create(
                file=(os.path.basename(path), fh.read()), model=settings.groq_whisper_model,
                response_format="verbose_json")
            provider, model, timed = "groq", settings.groq_whisper_model, True
        else:
            resp, timed = _openai_transcribe(fh, settings.openai_whisper_model)
            provider, model = "openai", settings.openai_whisper_model
    seconds = float(_seg_get(resp, "duration", 0) or 0) or length
    usage.record("transcribe", provider, model, audio_seconds=seconds)

    out = []
    for s in (_seg_get(resp, "segments") or []) if timed else []:
        text = (_seg_get(s, "text", "") or "").strip()
        if not text:
            continue
        start = float(_seg_get(s, "start", 0) or 0)
        end = float(_seg_get(s, "end", start) or start)
        out.append({"text": text, "start": offset + start, "duration": max(0.0, end - start)})
    if not out:
        out = _spread(_seg_get(resp, "text", "") or "", offset, seconds)
    return out


def transcribe_audio(path: str, progress: Optional[Progress] = None, base_progress: int = 15,
                     span: int = 25) -> list[Segment]:
    if not _whisper_ready():
        raise TranscriptError("Audio transcription needs GROQ_API_KEY or OPENAI_API_KEY.")
    # OpenAI's newer transcription models may return text without timestamps; shorter parts keep the
    # spread-out times within about two minutes of the truth. Cost is per minute either way.
    chunk = 600 if _use_groq_audio() else 120
    workdir = tempfile.mkdtemp(prefix="split_")
    try:
        parts = split_audio(path, workdir, chunk)
        segments: list[Segment] = []
        for i, (part, offset) in enumerate(parts):
            if progress:
                progress(f"Transcribing audio ({i + 1} of {len(parts)})", base_progress + int(span * i / len(parts)))
            segments.extend(transcribe_file(part, offset))
        if not segments:
            raise TranscriptError("No speech was found in the audio.")
        return segments
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Pasted text
# ---------------------------------------------------------------------------
_STAMP = re.compile(r"^\s*\[?((?:\d{1,2}:)?\d{1,2}:\d{2})\]?\s*[-–]?\s*(.*)$")


def segments_from_text(text: str) -> list[Segment]:
    """Turn pasted text into segments. Lines starting with 12:34 or [1:02:03] keep their times."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        raise TranscriptError("The pasted transcript is empty.")
    stamped = []
    for ln in lines:
        m = _STAMP.match(ln)
        if m and m.group(2):
            stamped.append({"text": m.group(2), "start": float(parse_time(m.group(1)) or 0), "duration": 0.0})
    if len(stamped) >= max(3, len(lines) // 2):
        return stamped
    # No timestamps: spread words out at roughly 150 words a minute so chunks still have rough times.
    words = " ".join(lines).split()
    segments, per = [], 40
    for i in range(0, len(words), per):
        segments.append({"text": " ".join(words[i:i + per]), "start": i / 150 * 60, "duration": per / 150 * 60})
    return segments


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------
def get_youtube_transcript(video_id: str, progress: Optional[Progress] = None) -> tuple[list[Segment], str]:
    """Returns (segments, method) where method is 'captions' or 'whisper'."""
    caption_error = None
    try:
        if progress:
            progress("Fetching captions from YouTube", 8)
        return fetch_captions(video_id), "captions"
    except Exception as e:
        caption_error = e
        log.info("Captions failed for %s: %s", video_id, e)

    if not _whisper_ready():
        raise TranscriptError(_explain_caption_error(caption_error) +
                              " Add GROQ_API_KEY to transcribe the audio instead, or paste the transcript.")
    workdir = tempfile.mkdtemp(prefix="yt_")
    try:
        if progress:
            progress("No captions available. Downloading the audio", 12)
        try:
            audio = download_audio(video_id, workdir)
        except Exception as e:
            raise TranscriptError(
                f"{_explain_caption_error(caption_error)} The audio download also failed ({_short(e)}). "
                "YouTube often blocks cloud servers: set YT_PROXY_URL or YTDLP_COOKIES_FILE, "
                "or upload the audio file / paste the transcript instead.") from e
        return transcribe_audio(audio, progress), "whisper"
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _short(e: Exception) -> str:
    return str(e).strip().splitlines()[0][:200] if str(e).strip() else e.__class__.__name__


def _explain_caption_error(e: Optional[Exception]) -> str:
    if e is None:
        return "Captions were not available."
    name = e.__class__.__name__
    if name in ("RequestBlocked", "IpBlocked"):
        return "YouTube blocked the caption request from this server."
    if name in ("TranscriptsDisabled", "NoTranscriptFound"):
        return "This video has no captions."
    return f"Captions were not available ({_short(e)})."


def list_playlist(url: str, limit: int) -> list[dict]:
    import yt_dlp
    opts = _ytdlp_opts({"extract_flat": "in_playlist", "playlistend": limit, "noplaylist": False})
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    items = []
    for e in (info or {}).get("entries") or []:
        vid = e.get("id")
        if vid and len(vid) == 11:
            items.append({"video_id": vid, "title": e.get("title") or ""})
    return items[:limit]


def channel_videos_url(channel_url: str) -> str:
    url = channel_url.strip().rstrip("/")
    if "list=" in url:
        return url
    if re.search(r"/(videos|streams|live)$", url):
        return url
    return url + "/videos"


def latest_channel_videos(channel_url: str, limit: int = 5) -> list[dict]:
    return list_playlist(channel_videos_url(channel_url), limit)
