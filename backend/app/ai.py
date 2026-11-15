"""One place to talk to the AI providers (Claude, OpenAI, Groq) and parse their JSON."""
import json
import logging
import re
from typing import Optional

from json_repair import repair_json

from . import usage
from .config import settings


class AIError(RuntimeError):
    pass


MODEL_LABELS = {"claude": "Claude", "openai": "OpenAI", "groq": "Groq"}


def resolve_model(choice: Optional[str]) -> str:
    """Pick the requested provider, or the first one that has a key."""
    available = settings.available_models()
    if not available:
        raise AIError("No AI key is configured. Set ANTHROPIC_API_KEY, OPENAI_API_KEY or GROQ_API_KEY.")
    choice = (choice or settings.default_model or "").lower()
    if choice in available:
        return choice
    return available[0]


# Which tier of model each job uses. "main" writes the documents; cheaper tiers do the simpler, frequent work.
TASK_TIERS = {
    "notes": "main",
    "notes_premium": "premium",
    "guide": "main",
    "ask": "fast",
    "verse": "fast",
    "start": "tiny",
}


def model_for(provider: str, task: str = "notes") -> str:
    return settings.models_for(provider)[TASK_TIERS.get(task, "main")]


def model_name(choice: str) -> str:
    return model_for(choice, "notes")


def _usage_numbers(u) -> tuple[int, int, int]:
    """(input, cached input, output) from an OpenAI/Groq or Anthropic usage object."""
    if u is None:
        return 0, 0, 0
    get = (lambda o, k: o.get(k) if isinstance(o, dict) else getattr(o, k, None))
    if get(u, "prompt_tokens") is not None:  # OpenAI / Groq
        details = get(u, "prompt_tokens_details")
        cached = (get(details, "cached_tokens") if details is not None else 0) or 0
        return int(get(u, "prompt_tokens") or 0), int(cached), int(get(u, "completion_tokens") or 0)
    cached = int(get(u, "cache_read_input_tokens") or 0)  # Anthropic reports cached reads separately
    return int(get(u, "input_tokens") or 0) + cached, cached, int(get(u, "output_tokens") or 0)


log = logging.getLogger("ai")

# OpenAI's GPT-5 family and Groq's gpt-oss models "think" before answering, and that thinking counts
# against the output limit. Long notes need room, so these get a bigger budget and low reasoning effort.
REASONING_HEADROOM = 3


class _Reply:
    def __init__(self, text: str, cut_off: bool, model: str = "", usage_obj=None):
        self.text, self.cut_off, self.model, self.usage = text, cut_off, model, usage_obj


def _is_param_error(e: Exception, name: str) -> bool:
    msg = str(e).lower()
    return name in msg and ("unsupported" in msg or "unrecognized" in msg or "not supported" in msg
                            or "unknown" in msg or "invalid" in msg)


def _chat(client, base: dict, extras: dict):
    """Call chat.completions, dropping optional parameters the model rejects."""
    kwargs = {**base, **extras}
    for _ in range(len(extras) + 1):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as e:
            dropped = next((k for k in list(kwargs) if k in extras and _is_param_error(e, k)), None)
            if not dropped:
                raise
            log.info("model rejected %s; retrying without it", dropped)
            kwargs.pop(dropped)
    return client.chat.completions.create(**kwargs)


def _complete(prompt: str, system: str, choice: str, max_tokens: int, want_json: bool,
              task: str = "notes") -> _Reply:
    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    model = model_for(choice, task)
    if choice == "claude":
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=3, timeout=900)
        # The system prompt is identical on every call, so mark it cacheable (cached reads cost 5-10%).
        msg = client.messages.create(model=model, max_tokens=max_tokens,
                                     system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                                     messages=[{"role": "user", "content": prompt}])
        text = "".join(getattr(b, "text", "") for b in msg.content)
        return _Reply(text, getattr(msg, "stop_reason", "") == "max_tokens", model, getattr(msg, "usage", None))

    if choice == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key, max_retries=3, timeout=900)
        base = dict(model=model, messages=messages,
                    max_completion_tokens=max_tokens * REASONING_HEADROOM)
        extras = {"reasoning_effort": "low"}
        if want_json:
            extras["response_format"] = {"type": "json_object"}
        resp = _chat(client, base, extras)
    elif choice == "groq":
        from groq import Groq
        client = Groq(api_key=settings.groq_api_key, max_retries=3, timeout=900)
        base = dict(model=model, messages=messages,
                    max_tokens=min(max_tokens * REASONING_HEADROOM, 65000))
        extras = {"reasoning_effort": "low"}
        if want_json:
            extras["response_format"] = {"type": "json_object"}
        resp = _chat(client, base, extras)
    else:
        raise AIError(f"Unknown model: {choice}")

    choice0 = resp.choices[0]
    text = choice0.message.content or ""
    cut_off = getattr(choice0, "finish_reason", "") == "length"
    if not text.strip():
        log.warning("%s returned no text (finish_reason=%s)", choice, getattr(choice0, "finish_reason", ""))
    return _Reply(text, cut_off, model, getattr(resp, "usage", None))


def complete(prompt: str, system: str, model_choice: Optional[str] = None,
             max_tokens: int = 4096, want_json: bool = False, task: str = "notes") -> str:
    choice = resolve_model(model_choice)
    try:
        reply = _complete(prompt, system, choice, max_tokens, want_json, task)
    except AIError:
        raise
    except Exception as e:  # provider SDK errors vary; surface a readable message
        raise AIError(f"{MODEL_LABELS.get(choice, choice)} request failed: {e}") from e
    inp, cached, out = _usage_numbers(reply.usage)
    usage.record(task, choice, reply.model or model_for(choice, task), inp, cached, out)
    if not reply.text.strip():
        raise AIError(f"{MODEL_LABELS[choice]} returned an empty reply"
                      f"{' (it ran out of room)' if reply.cut_off else ''}. Try again or pick another model.")
    return reply.text


def parse_json(raw: str) -> dict:
    """Parse a model's JSON reply, tolerating code fences, chatter and truncation."""
    text = (raw or "").strip()
    text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    if start > 0:
        text = text[start:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    repaired = repair_json(text, return_objects=True)
    if isinstance(repaired, dict) and repaired:
        return repaired
    raise AIError("The AI reply was not valid JSON. Try again or pick another model.")


def complete_json(prompt: str, system: str, model_choice: Optional[str] = None,
                  max_tokens: int = 4096, attempts: int = 2, task: str = "notes") -> dict:
    """Ask for JSON; on an empty, cut-off or unparseable reply, try once more before giving up."""
    last: Optional[AIError] = None
    for attempt in range(attempts):
        try:
            return parse_json(complete(prompt, system, model_choice, max_tokens=max_tokens, want_json=True, task=task))
        except AIError as e:
            last = e
            if "request failed" in str(e):  # auth, quota, network: retrying won't help
                raise
            log.warning("JSON attempt %d failed: %s", attempt + 1, e)
    raise last


def embeddings_available() -> bool:
    return bool(settings.openai_api_key and settings.embeddings_enabled)


def embed(texts: list[str]) -> Optional[list[list[float]]]:
    """Embed texts with OpenAI, or return None when embeddings are not configured."""
    if not embeddings_available() or not texts:
        return None
    from openai import OpenAI
    client = OpenAI(api_key=settings.openai_api_key, max_retries=3, timeout=120)
    out: list[list[float]] = []
    for i in range(0, len(texts), 96):
        resp = client.embeddings.create(model=settings.embedding_model, input=texts[i:i + 96])
        out.extend(d.embedding for d in resp.data)
        u = getattr(resp, "usage", None)
        usage.record("embed", "openai", settings.embedding_model,
                     input_tokens=int(getattr(u, "prompt_tokens", 0) or getattr(u, "total_tokens", 0) or 0))
    return out
