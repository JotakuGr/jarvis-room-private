"""Inventário local Ollama sem inferência; seleção explícita e limites por sessão."""

from __future__ import annotations

import http.client
import json
import re
from dataclasses import dataclass

from .voice_contract import VoiceError

OLLAMA_ENDPOINT = "http://127.0.0.1:11434"


@dataclass(frozen=True, slots=True)
class LLMSettings:
    model: str
    max_tokens: int = 192
    context_tokens: int = 4096
    max_model_bytes: int = 4 * 1024**3

    def __post_init__(self) -> None:
        if (
            not isinstance(self.model, str)
            or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,127}", self.model)
            or "://" in self.model
        ):
            raise ValueError("llm_invalid_model")
        if type(self.max_tokens) is not int or not 32 <= self.max_tokens <= 512:
            raise ValueError("llm_invalid_token_limit")
        if (
            type(self.context_tokens) is not int
            or not 2048 <= self.context_tokens <= 8192
        ):
            raise ValueError("llm_invalid_context_limit")
        if (
            type(self.max_model_bytes) is not int
            or not 0 < self.max_model_bytes <= 8 * 1024**3
        ):
            raise ValueError("llm_invalid_model_size_limit")


def ollama_get(path: str, *, timeout: float = 2) -> dict:
    if path not in {"/api/tags", "/api/ps", "/api/version"}:
        raise VoiceError("llm_endpoint_forbidden")
    connection = http.client.HTTPConnection("127.0.0.1", 11434, timeout=timeout)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        if response.status != 200:
            raise VoiceError("llm_server_unavailable")
        raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise VoiceError("llm_inventory_limit")
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise VoiceError("llm_invalid_inventory")
        return result
    except (OSError, ValueError, http.client.HTTPException) as exc:
        raise VoiceError("llm_server_unavailable") from exc
    finally:
        connection.close()


def local_models() -> list[dict]:
    models = ollama_get("/api/tags").get("models")
    if not isinstance(models, list) or len(models) > 256:
        raise VoiceError("llm_invalid_inventory")
    result = []
    for item in models:
        if not isinstance(item, dict):
            raise VoiceError("llm_invalid_inventory")
        name, size = item.get("name"), item.get("size")
        if not isinstance(name, str) or type(size) is not int or size < 0:
            raise VoiceError("llm_invalid_inventory")
        result.append(
            {
                "name": name,
                "size_bytes": size,
                "digest": item.get("digest"),
                "details": item.get("details", {}),
            }
        )
    return result


def require_model(settings: LLMSettings, models: list[dict] | None = None) -> dict:
    for item in local_models() if models is None else models:
        if item["name"] == settings.model:
            if item["size_bytes"] > settings.max_model_bytes:
                raise VoiceError("llm_model_resource_limit")
            return item.copy()
    raise VoiceError("llm_model_not_installed")
