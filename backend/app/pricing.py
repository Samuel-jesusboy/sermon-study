"""List prices in US dollars, used to estimate what each AI call cost.

Checked November 2026 against the providers' pricing pages. Prices change: update them here, or override
any model with the PRICE_OVERRIDES environment variable, e.g.
  PRICE_OVERRIDES={"gpt-5.4": [2.5, 0.25, 15]}
Text models are [input, cached input, output] per 1M tokens. Audio models are per minute of audio.
"""
import json
import logging
import os
from typing import Optional

log = logging.getLogger("pricing")

TEXT_PRICES: dict[str, tuple[float, float, float]] = {
    # OpenAI
    "gpt-5.5": (5.00, 0.50, 30.00),
    "gpt-5.4": (2.50, 0.25, 15.00),
    "gpt-5.4-mini": (0.75, 0.075, 4.50),
    "gpt-5.4-nano": (0.20, 0.02, 1.25),
    "text-embedding-3-small": (0.02, 0.02, 0.0),
    "text-embedding-3-large": (0.13, 0.13, 0.0),
    # Anthropic
    "claude-opus-5-5": (4.00, 0.20, 20.00),
    "claude-sonnet-5-5": (2.00, 0.10, 10.00),
    "claude-haiku-5-5": (0.10, 0.01, 0.50),  # prompts up to 100K tokens; 5x above that
    # Groq
    "openai/gpt-oss-120b": (0.15, 0.075, 0.60),
    "openai/gpt-oss-20b": (0.075, 0.0375, 0.30),
}

AUDIO_PER_MINUTE: dict[str, float] = {
    "gpt-transcribe": 0.0045,
    "whisper-1": 0.006,
    "gpt-4o-transcribe": 0.006,
    "gpt-4o-mini-transcribe": 0.003,
    "whisper-large-v3-turbo": 0.04 / 60,  # Groq, $0.04 per hour
    "whisper-large-v3": 0.111 / 60,       # Groq, $0.111 per hour
}


def _overrides() -> dict:
    raw = os.getenv("PRICE_OVERRIDES", "").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        log.warning("PRICE_OVERRIDES is not valid JSON; ignoring it")
        return {}


def text_price(model: str) -> Optional[tuple[float, float, float]]:
    o = _overrides().get(model)
    if isinstance(o, (list, tuple)) and len(o) == 3:
        return tuple(float(x) for x in o)
    return TEXT_PRICES.get(model)


def text_cost(model: str, input_tokens: int, cached_tokens: int, output_tokens: int) -> Optional[float]:
    price = text_price(model)
    if not price:
        return None
    p_in, p_cached, p_out = price
    if model == "claude-haiku-5-5" and input_tokens > 100_000:
        p_in, p_cached, p_out = p_in * 5, p_cached * 5, p_out * 5
    uncached = max(0, input_tokens - cached_tokens)
    return round((uncached * p_in + cached_tokens * p_cached + output_tokens * p_out) / 1_000_000, 6)


def audio_cost(model: str, seconds: float) -> Optional[float]:
    o = _overrides().get(model)
    per_min = float(o) if isinstance(o, (int, float)) else AUDIO_PER_MINUTE.get(model)
    if per_min is None:
        return None
    billed = max(seconds, 10.0) if model.startswith("whisper-large") else seconds  # Groq bills at least 10s
    return round(billed / 60 * per_min, 6)
