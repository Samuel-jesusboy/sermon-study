"""One place to talk to the AI providers (Claude, OpenAI, Groq) and parse their JSON."""
import json
import re
from typing import Optional

from json_repair import repair_json

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


def model_name(choice: str) -> str:
    return {
        "claude": settings.claude_model,
        "openai": settings.openai_model,
        "groq": settings.groq_model,
    }[choice]


def complete(prompt: str, system: str, model_choice: Optional[str] = None,
             max_tokens: int = 4096, want_json: bool = False) -> str:
    choice = resolve_model(model_choice)
    try:
        if choice == "claude":
            import anthropic
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=3, timeout=600)
            msg = client.messages.create(
                model=settings.claude_model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(getattr(b, "text", "") for b in msg.content)
            if getattr(msg, "stop_reason", "") == "max_tokens" and want_json:
                # The JSON was cut off; repair_json below will close it as best it can.
                pass
            return text

        if choice == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=settings.openai_api_key, max_retries=3, timeout=600)
            kwargs = dict(
                model=settings.openai_model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                max_completion_tokens=max_tokens,
            )
            if want_json:
                kwargs["response_format"] = {"type": "json_object"}
            resp = client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content or ""

        if choice == "groq":
            from groq import Groq
            client = Groq(api_key=settings.groq_api_key, max_retries=3, timeout=600)
            kwargs = dict(
                model=settings.groq_model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                max_tokens=max_tokens,
            )
            if want_json:
                kwargs["response_format"] = {"type": "json_object"}
            resp = client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content or ""
    except AIError:
        raise
    except Exception as e:  # provider SDK errors vary; surface a readable message
        raise AIError(f"{MODEL_LABELS.get(choice, choice)} request failed: {e}") from e
    raise AIError(f"Unknown model: {choice}")


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
                  max_tokens: int = 4096) -> dict:
    return parse_json(complete(prompt, system, model_choice, max_tokens=max_tokens, want_json=True))


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
    return out
