"""Database access through Supabase's REST API (PostgREST).

Each client carries one user's access token, so Postgres row-level security
applies to every query: a user can only ever read and write their own rows.
"""
from postgrest import SyncPostgrestClient

from .config import settings


class ConfigError(RuntimeError):
    pass


def _check_config() -> None:
    if not settings.supabase_url or not settings.supabase_key:
        raise ConfigError("SUPABASE_URL and SUPABASE_KEY must be set (see backend/.env.example)")


def user_db(access_token: str) -> SyncPostgrestClient:
    """A client that acts as the signed-in user."""
    _check_config()
    return SyncPostgrestClient(
        f"{settings.supabase_url}/rest/v1",
        headers={
            "apikey": settings.supabase_key,
            "Authorization": f"Bearer {access_token}",
        },
        timeout=30,
    )


def anon_db() -> SyncPostgrestClient:
    """A client with no user: it can only see rows that RLS makes public."""
    _check_config()
    return SyncPostgrestClient(
        f"{settings.supabase_url}/rest/v1",
        headers={
            "apikey": settings.supabase_key,
            "Authorization": f"Bearer {settings.supabase_key}",
        },
        timeout=30,
    )
