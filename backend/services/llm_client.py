import asyncio
import json
import logging
import re
import time
from typing import Any, Optional

import httpx

from config import settings

logger = logging.getLogger("codeonboard.llm")

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
TRANSIENT_STATUS = {500, 502, 503, 504}


class LLMError(RuntimeError):
    pass


class GeminiClient:
    """Async Gemini REST client: bounded concurrency, fast failover across models, and 429 cooldowns."""

    def __init__(self) -> None:
        self.models = list(dict.fromkeys([settings.gemini_model, *settings.gemini_fallback_models]))
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(settings.llm_timeout_seconds, connect=15.0))
        self._semaphore = asyncio.Semaphore(settings.llm_max_concurrency)
        self._cooldown_until: dict[str, float] = {}

    @property
    def configured(self) -> bool:
        return settings.llm_configured

    async def close(self) -> None:
        await self._client.aclose()

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        json_mode: bool = False,
        temperature: float = 0.3,
        max_tokens: int = 8192,
        deadline_seconds: float = 240.0,
    ) -> str:
        if not self.configured:
            raise LLMError("GEMINI_API_KEY is not set")

        generation_config: dict[str, Any] = {"temperature": temperature, "maxOutputTokens": max_tokens}
        if json_mode:
            generation_config["responseMimeType"] = "application/json"
        if settings.gemini_thinking_level:
            generation_config["thinkingConfig"] = {"thinkingLevel": settings.gemini_thinking_level}
        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": generation_config,
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        deadline = time.monotonic() + deadline_seconds
        async with self._semaphore:
            return await self._generate(body, deadline)

    async def _generate(self, body: dict[str, Any], deadline: float) -> str:
        last_error = "no model available"
        for round_number in range(2):
            for model in await self._available_models():
                for attempt in range(2):
                    remaining = deadline - time.monotonic()
                    if remaining < 5:
                        raise LLMError(f"deadline exceeded ({last_error})")
                    try:
                        response = await self._client.post(
                            f"{API_BASE}/{model}:generateContent",
                            headers={"x-goog-api-key": settings.gemini_api_key},
                            json=body,
                            timeout=httpx.Timeout(min(settings.llm_timeout_seconds, remaining), connect=15.0),
                        )
                    except httpx.TimeoutException:
                        last_error = f"{model}: timed out"
                        break
                    except httpx.HTTPError as exc:
                        last_error = f"{model}: {exc!r}"
                        await asyncio.sleep(1 + attempt)
                        continue

                    status = response.status_code
                    if status == 200:
                        text = _extract_text(response.json())
                        if text:
                            return text
                        last_error = f"{model}: empty response"
                        break
                    last_error = f"{model}: HTTP {status} {_error_message(response)}"
                    if status == 429:
                        self._cooldown_until[model] = time.monotonic() + _retry_delay(response)
                        break
                    if status in TRANSIENT_STATUS:
                        await asyncio.sleep(1 + attempt)
                        continue
                    self._cooldown_until[model] = time.monotonic() + 3600
                    break
                logger.warning("Gemini call failed, failing over: %s", last_error)
            if round_number == 0:
                await asyncio.sleep(3)
        raise LLMError(last_error)

    async def _available_models(self) -> list[str]:
        now = time.monotonic()
        ready = [m for m in self.models if self._cooldown_until.get(m, 0) <= now]
        if ready:
            return ready
        soonest = min(self.models, key=lambda m: self._cooldown_until.get(m, 0))
        await asyncio.sleep(min(20.0, max(0.0, self._cooldown_until[soonest] - now)))
        return [soonest]

    async def generate_json(self, prompt: str, system: Optional[str] = None, **kwargs: Any) -> Any:
        text = await self.generate(prompt, system=system, json_mode=True, **kwargs)
        return parse_json_loose(text)


def _extract_text(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        return ""
    parts = (candidates[0].get("content") or {}).get("parts") or []
    return "".join(part.get("text", "") for part in parts if not part.get("thought")).strip()


def _error_message(response: httpx.Response) -> str:
    try:
        error = response.json()["error"]
    except (ValueError, KeyError, TypeError):
        return response.text[:160]
    quotas = [
        v.get("quotaId", "")
        for detail in error.get("details", [])
        for v in detail.get("violations", [])
        if isinstance(v, dict)
    ]
    message = str(error.get("message", ""))[:120]
    return f"{message} [quota: {', '.join(q for q in quotas if q)}]" if any(quotas) else message


def _retry_delay(response: httpx.Response) -> float:
    try:
        for detail in response.json()["error"].get("details", []):
            delay = detail.get("retryDelay")
            if delay:
                return min(120.0, float(str(delay).rstrip("s")))
    except (ValueError, KeyError, TypeError):
        pass
    return 30.0


def parse_json_loose(text: str) -> Any:
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    start = min((i for i in (cleaned.find("{"), cleaned.find("[")) if i != -1), default=-1)
    if start != -1:
        end = max(cleaned.rfind("}"), cleaned.rfind("]"))
        candidate = re.sub(r",\s*([}\]])", r"\1", cleaned[start : end + 1])
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    raise LLMError(f"Model did not return valid JSON: {text[:200]}")
