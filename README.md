# Sermon Study

Turn every sermon into full study notes you can search, ask questions of, and share.

Paste a YouTube link (or upload a recording, or paste a transcript) and Sermon Study writes complete notes: each main point in full, illustrations, every scripture in context, quotes, applications, prayer points, study questions and a small-group guide, all linked to the minute in the video where it was said.

## Features

- **Full sermon notes**, not summaries, with the worship and announcements skipped automatically
- **Four ways in:** YouTube video, YouTube playlist, audio/video upload, or pasted transcript
- **Background processing** with live progress, so long sermons and playlists never time out
- **Clickable timestamps:** every section, verse and quote jumps the in-page player to that moment
- **Ask your library:** questions are answered from your own sermons, citing the sermon and minute (semantic search with OpenAI embeddings, or Postgres full-text search without them)
- **Explain a verse**, connected to what your pastors have preached on it
- **Browse by topic, Bible book or church**, plus search
- **Churches:** save the channels you follow, pull in their latest sermons with one tap, or auto-import new ones
- **Study guides:** multi-week plans for personal devotions, small groups / house fellowships, or family
- **Share:** a public read-only link per sermon, WhatsApp share, copy as Markdown, download, print / save as PDF
- **Accounts:** email sign-in with Supabase Auth; row-level security keeps each person's library private
- **Choice of AI:** Claude, OpenAI or Groq, whichever keys you set

## How it works

```
React (Netlify) ──► FastAPI (Render/Railway, Docker) ──► Supabase Postgres (RLS, pgvector)
     │                    │
     └─ Supabase Auth     ├─ YouTube captions ─► fallback: yt-dlp audio ─► Whisper (Groq/OpenAI)
                          └─ Claude / OpenAI / Groq for notes, Ask, study guides
```

The backend never uses a service-role key. Every database call is made with the signed-in user's token, so Postgres row-level security decides what each request can read or write.

## Run it locally

You need Python 3.10+, Node 20+, ffmpeg (for audio transcription) and a Supabase project.

**1. Database.** In your Supabase project's SQL editor, run the files in `supabase/migrations/` in order (or use `supabase db push` with the Supabase CLI). Then in **Authentication → URL Configuration**, set the Site URL to `http://localhost:3000` (and later your Netlify URL).

**2. Backend.**

```bash
cd backend
cp .env.example .env        # fill in SUPABASE_URL, SUPABASE_KEY and at least one AI key
pip install -r requirements.txt
uvicorn main:app --reload   # http://localhost:8000/docs
```

**3. Frontend.**

```bash
cd frontend
cp .env.example .env        # same Supabase URL and anon key, plus REACT_APP_API_URL
npm install
npm start                   # http://localhost:3000
```

**Tests:** `cd backend && pip install pytest && python -m pytest -q`

## Deploy

**Backend on Render:** New → Blueprint → choose this repo. `render.yaml` builds `backend/Dockerfile` (which includes ffmpeg). Fill in the environment variables when asked. Use a paid instance: free instances sleep and interrupt background jobs. Railway and Fly.io work with the same Dockerfile.

**Frontend on Netlify:** Add new site → Import from Git → this repo. `netlify.toml` sets the build. Add `REACT_APP_API_URL` (your Render URL), `REACT_APP_SUPABASE_URL` and `REACT_APP_SUPABASE_KEY` under Environment variables, then redeploy. Finally set `CORS_ORIGINS` and `APP_URL` on the backend to your Netlify URL, and add the Netlify URL to Supabase's redirect URLs.

## YouTube on a hosted server

YouTube blocks caption requests from most cloud servers, so a link that works on your laptop can fail once deployed. Sermon Study tries captions first, then downloads the audio and transcribes it with Whisper. If both are blocked:

- set `YT_PROXY_URL` (any HTTP proxy) or `WEBSHARE_PROXY_USERNAME` / `WEBSHARE_PROXY_PASSWORD` (residential proxies), and/or
- set `YTDLP_COOKIES_FILE` to a cookies file exported from a browser signed in to YouTube, or
- use **Upload audio** or **Paste transcript**, which skip YouTube entirely.

## Configuration

All settings are environment variables; see `backend/.env.example`. The useful ones:

| Variable | Default | Purpose |
| --- | --- | --- |
| `CLAUDE_MODEL` / `OPENAI_MODEL` / `GROQ_MODEL` | `claude-sonnet-5-5` / `gpt-5.5` / `openai/gpt-oss-120b` | Change models without code changes |
| `DEFAULT_AI` | `claude` | Provider used when the user hasn't picked one |
| `EMBEDDINGS_ENABLED` | `true` | Semantic search for Ask (needs `OPENAI_API_KEY`) |
| `MONTHLY_SERMON_LIMIT` | `0` (unlimited) | Per-user monthly cap |
| `PLAYLIST_MAX_VIDEOS` | `25` | Max videos queued from one playlist |
| `JOB_WORKERS` | `2` | Sermons processed at the same time |

## Bible translations

The Bible reader uses [bible-api.com](https://bible-api.com) and offers public-domain translations (KJV, WEB, BBE, OEB). NIV, ESV and NKJV are licensed; adding them needs a licensed API such as API.Bible.

## Project layout

```
backend/            FastAPI app (main.py, app/), tests, Dockerfile
frontend/           React app (Create React App)
supabase/migrations SQL schema, row-level security, search functions
render.yaml         Render blueprint for the backend
netlify.toml        Netlify config for the frontend
```
