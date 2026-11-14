"""Sign-in check for API requests.

The frontend signs in with Supabase Auth and sends `Authorization: Bearer <token>`.
We ask Supabase who the token belongs to (cached briefly so job polling stays cheap).
"""
import threading
import time
from dataclasses import dataclass

import httpx
from fastapi import Header, HTTPException

from .config import settings
from .db import user_db

_CACHE_SECONDS = 60
_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()


@dataclass
class CurrentUser:
    id: str
    email: str
    token: str

    @property
    def db(self):
        return user_db(self.token)


def _lookup(token: str) -> dict:
    now = time.time()
    with _lock:
        hit = _cache.get(token)
        if hit and now - hit[0] < _CACHE_SECONDS:
            return hit[1]
    try:
        resp = httpx.get(
            f"{settings.supabase_url}/auth/v1/user",
            headers={"apikey": settings.supabase_key, "Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Could not reach the sign-in service: {e}")
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Your session has expired. Please sign in again.")
    user = resp.json()
    with _lock:
        if len(_cache) > 1000:
            _cache.clear()
        _cache[token] = (now, user)
    return user


def get_current_user(authorization: str = Header(default="")) -> CurrentUser:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Please sign in.")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Please sign in.")
    user = _lookup(token)
    return CurrentUser(id=user["id"], email=user.get("email") or "", token=token)
