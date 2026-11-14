"""Settings, read once from environment variables (or a local .env file)."""
import os
from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    raw = _env(name, "true" if default else "false").lower()
    return raw in ("1", "true", "yes", "on")


class Settings:
    # Supabase. SUPABASE_KEY is the public anon/publishable key: every query runs
    # with the signed-in user's token, so row-level security decides what they see.
    supabase_url = _env("SUPABASE_URL").rstrip("/")
    supabase_key = _env("SUPABASE_KEY")

    # AI providers (set at least one)
    anthropic_api_key = _env("ANTHROPIC_API_KEY")
    openai_api_key = _env("OPENAI_API_KEY")
    groq_api_key = _env("GROQ_API_KEY")

    # Model names live here, not in code, so a retired model is a config change.
    claude_model = _env("CLAUDE_MODEL", "claude-sonnet-5-5")
    openai_model = _env("OPENAI_MODEL", "gpt-5.5")
    groq_model = _env("GROQ_MODEL", "openai/gpt-oss-120b")
    default_model = _env("DEFAULT_AI", "claude")
    notes_max_tokens = _int("NOTES_MAX_TOKENS", 16000)

    # Search: embeddings need OPENAI_API_KEY; without it, Ask uses full-text search.
    embedding_model = _env("EMBEDDING_MODEL", "text-embedding-3-small")
    embeddings_enabled = _bool("EMBEDDINGS_ENABLED", True)

    # Transcripts. YouTube blocks most cloud-server IPs, so on a hosted server set a
    # residential proxy (Webshare or any HTTP proxy) and/or a cookies file for yt-dlp.
    yt_proxy_url = _env("YT_PROXY_URL")
    webshare_username = _env("WEBSHARE_PROXY_USERNAME")
    webshare_password = _env("WEBSHARE_PROXY_PASSWORD")
    ytdlp_cookies_file = _env("YTDLP_COOKIES_FILE")
    transcript_languages = [x.strip() for x in _env("TRANSCRIPT_LANGUAGES", "en,en-US,en-GB,en-NG").split(",") if x.strip()]
    whisper_provider = _env("WHISPER_PROVIDER", "groq")  # groq | openai
    groq_whisper_model = _env("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo")
    openai_whisper_model = _env("OPENAI_WHISPER_MODEL", "whisper-1")
    max_upload_mb = _int("MAX_UPLOAD_MB", 200)

    # Jobs and limits
    job_workers = _int("JOB_WORKERS", 2)
    monthly_sermon_limit = _int("MONTHLY_SERMON_LIMIT", 0)  # 0 = unlimited
    playlist_max_videos = _int("PLAYLIST_MAX_VIDEOS", 25)

    # Comma-separated list of allowed browser origins, or * for any.
    cors_origins = [x.strip() for x in _env("CORS_ORIGINS", "*").split(",") if x.strip()]

    # Public link base used in share text (the frontend URL).
    app_url = _env("APP_URL", "http://localhost:3000").rstrip("/")

    def available_models(self) -> list[str]:
        models = []
        if self.anthropic_api_key:
            models.append("claude")
        if self.openai_api_key:
            models.append("openai")
        if self.groq_api_key:
            models.append("groq")
        return models


settings = Settings()
