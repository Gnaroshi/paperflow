from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from paperflow.utils import dump_json_data


ZOTERO_KEY_CURRENT_URL = "https://api.zotero.org/keys/current"
GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


def redact_secret(value: str | None, prefix: str) -> str:
    if not value:
        return f"{prefix}_not_set"
    return f"{prefix}_{'*' * 8}{value[-4:]}"


def keychain_read(account: str, service: str = "PaperFlow") -> str | None:
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-a", account, "-w"],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def api_key_from_env_or_keychain(env_name: str, account: str) -> str | None:
    return os.environ.get(env_name) or keychain_read(account)


def validate_numeric_user_id(value: str | int | None) -> str:
    text = "" if value is None else str(value).strip()
    if not text.isdigit():
        raise ValueError("Zotero user ID must be numeric, not an email address or username.")
    return text


def parse_zotero_key_response(payload: dict[str, Any]) -> dict[str, Any]:
    access = payload.get("access") or {}
    user_access = access.get("user") if isinstance(access.get("user"), dict) else {}
    user_id = payload.get("userID") or payload.get("userId") or payload.get("user_id")
    parsed = {
        "ok": True,
        "userID": int(validate_numeric_user_id(user_id)),
        "username": payload.get("username"),
        "access": {
            "user": {
                "library": bool(user_access.get("library")),
                "write": bool(user_access.get("write")),
                "notes": bool(user_access.get("notes")),
                "files": bool(user_access.get("files")),
            }
        },
    }
    return parsed


def zotero_key_has_write_access(parsed: dict[str, Any]) -> bool:
    return bool((((parsed.get("access") or {}).get("user") or {}).get("write")))


def verify_zotero_api_key(
    api_key: str | None = None,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    key = api_key or api_key_from_env_or_keychain("ZOTERO_API_KEY", "ZOTERO_API_KEY")
    if not key:
        raise ValueError("ZOTERO_API_KEY is not set.")
    close_client = client is None
    client = client or httpx.Client(timeout=20)
    try:
        response = client.get(ZOTERO_KEY_CURRENT_URL, headers={"Zotero-API-Key": key})
        response.raise_for_status()
        return parse_zotero_key_response(response.json())
    finally:
        if close_client:
            client.close()


@dataclass
class GeminiError:
    error_type: str
    message: str
    status_code: int | None = None


def classify_gemini_error(status_code: int, payload: dict[str, Any] | None = None) -> GeminiError:
    status = ((payload or {}).get("error") or {}).get("status")
    if status_code == 429 or status == "RESOURCE_EXHAUSTED":
        return GeminiError(
            "rate_limited",
            "Gemini free quota/rate limit reached or temporarily exceeded",
            status_code,
        )
    if status_code in {401, 403}:
        return GeminiError("invalid_key", "Invalid or unauthorized Gemini API key", status_code)
    if 500 <= status_code <= 599:
        return GeminiError("service_error", "Gemini service error", status_code)
    return GeminiError("request_failed", "Gemini request failed", status_code)


def parse_gemini_usage(payload: dict[str, Any]) -> dict[str, int]:
    usage = payload.get("usageMetadata") or {}
    return {
        "promptTokenCount": int(usage.get("promptTokenCount") or 0),
        "candidatesTokenCount": int(usage.get("candidatesTokenCount") or 0),
        "totalTokenCount": int(usage.get("totalTokenCount") or 0),
    }


def usage_path_for_day(day: date | None = None, root: Path = Path("data")) -> Path:
    day = day or datetime.now().date()
    return root / f"gemini_usage_{day.isoformat()}.json"


def load_gemini_usage(path: Path | None = None) -> dict[str, Any]:
    path = path or usage_path_for_day()
    if not path.exists():
        return {
            "date": datetime.now().date().isoformat(),
            "request_count": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "failed_rate_limit_calls": 0,
            "last_429_resource_exhausted_time": None,
        }
    return json.loads(path.read_text(encoding="utf-8"))


def record_gemini_usage(
    usage: dict[str, int] | None = None,
    error_type: str | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    path = path or usage_path_for_day()
    current = load_gemini_usage(path)
    current["request_count"] = int(current.get("request_count") or 0) + 1
    if usage:
        current["input_tokens"] = int(current.get("input_tokens") or 0) + usage.get(
            "promptTokenCount", 0
        )
        current["output_tokens"] = int(current.get("output_tokens") or 0) + usage.get(
            "candidatesTokenCount", 0
        )
        current["total_tokens"] = int(current.get("total_tokens") or 0) + usage.get(
            "totalTokenCount", 0
        )
    if error_type == "rate_limited":
        current["failed_rate_limit_calls"] = int(current.get("failed_rate_limit_calls") or 0) + 1
        current["last_429_resource_exhausted_time"] = datetime.now(timezone.utc).isoformat()
    dump_json_data(path, current)
    return current


class GeminiClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_GEMINI_MODEL,
        base_url: str = GEMINI_API_BASE_URL,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key or api_key_from_env_or_keychain("GEMINI_API_KEY", "GEMINI_API_KEY")
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def generate(self, prompt: str) -> dict[str, Any]:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set.")
        url = f"{self.base_url}/models/{self.model}:generateContent"
        response = self.client.post(
            url,
            params={"key": self.api_key},
            json={"contents": [{"parts": [{"text": prompt}]}]},
        )
        if response.status_code >= 400:
            try:
                payload = response.json()
            except Exception:
                payload = {}
            error = classify_gemini_error(response.status_code, payload)
            record_gemini_usage(error_type=error.error_type)
            return {"ok": False, "error_type": error.error_type, "message": error.message}
        payload = response.json()
        usage = parse_gemini_usage(payload)
        record_gemini_usage(usage=usage)
        return {"ok": True, "model": self.model, "usage": usage, "raw": payload}


def verify_gemini_api_key(
    api_key: str | None = None,
    model: str = DEFAULT_GEMINI_MODEL,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    gemini = GeminiClient(api_key=api_key, model=model, client=client)
    try:
        result = gemini.generate("Reply with the single word OK.")
        if not result.get("ok"):
            return result
        return {"ok": True, "model": model, "usage": result["usage"]}
    finally:
        gemini.close()
