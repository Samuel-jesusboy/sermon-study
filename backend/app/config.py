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

    # Each provider has four tiers, and each job uses the tier that fits it (see TASK_TIERS in ai.py):
    #   main    - writing sermon documents and study guides (the product; quality matters most)
    #   premium - an optional upgrade for important sermons
    #   fast    - Ask and verse explanations (frequent, short, grounded in excerpts)
    #   tiny    - finding where the sermon starts (a simple classification)
    # The older single-model variables (OPENAI_MODEL, CLAUDE_MODEL, GROQ_MODEL) still set the main tier.
    openai_models = {
        "main": _env("OPENAI_MODEL_MAIN", _env("OPENAI_MODEL", "gpt-5.4")),
        "premium": _env("OPENAI_MODEL_PREMIUM", "gpt-5.5"),
        "fast": _env("OPENAI_MODEL_FAST", "gpt-5.4-mini"),
        "tiny": _env("OPENAI_MODEL_TINY", "gpt-5.4-nano"),
    }
    claude_models = {
        "main": _env("CLAUDE_MODEL_MAIN", _env("CLAUDE_MODEL", "claude-sonnet-5-5")),
        "premium": _env("CLAUDE_MODEL_PREMIUM", "claude-opus-5-5"),
        "fast": _env("CLAUDE_MODEL_FAST", "claude-haiku-5-5"),
        "tiny": _env("CLAUDE_MODEL_TINY", "claude-haiku-5-5"),
    }
    groq_models = {
        "main": _env("GROQ_MODEL_MAIN", _env("GROQ_MODEL", "openai/gpt-oss-120b")),
        "premium": _env("GROQ_MODEL_PREMIUM", "openai/gpt-oss-120b"),
        "fast": _env("GROQ_MODEL_FAST", "openai/gpt-oss-120b"),
        "tiny": _env("GROQ_MODEL_TINY", "openai/gpt-oss-20b"),
    }
    default_model = _env("DEFAULT_AI", "openai")
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
    # Turbo is $0.04/hour; set whisper-large-v3 ($0.111/hour) for more accuracy on accented speech.
    groq_whisper_model = _env("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo")
    # whisper-1 is deprecated (removed Feb 2027); gpt-transcribe is OpenAI's replacement.
    openai_whisper_model = _env("OPENAI_WHISPER_MODEL", "gpt-transcribe")
    max_upload_mb = _int("MAX_UPLOAD_MB", 200)

    # Jobs and limits
    job_workers = _int("JOB_WORKERS", 2)
    monthly_sermon_limit = _int("MONTHLY_SERMON_LIMIT", 0)  # 0 = unlimited
    playlist_max_videos = _int("PLAYLIST_MAX_VIDEOS", 25)

    # Comma-separated list of allowed browser origins, or * for any.
    cors_origins = [x.strip() for x in _env("CORS_ORIGINS", "*").split(",") if x.strip()]

    # Public link base used in share text (the frontend URL).
    app_url = _env("APP_URL", "http://localhost:3000").rstrip("/")

    def models_for(self, provider: str) -> dict:
        return {"openai": self.openai_models, "claude": self.claude_models, "groq": self.groq_models}[provider]

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
