"""DeepSeek provider adapter. Uses sync httpx.Client; holds the API key."""

import json
import logging
from typing import Any, Iterator

import httpx
import jsonschema
import jsonschema.exceptions

from apps.gateway.adapters.base import (
    BaseProviderAdapter,
    ProviderAuthError,
    ProviderClientError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderValidationError,
)
from apps.gateway.execution.streaming import parse_sse_line
from core.contracts.model_router import (
    ModelCallRequest,
    ModelCallResponse,
    UsageSummary,
)
from core.model_router.domain.models import ModelSpec
from core.model_router.domain.streaming import StreamError, StreamingEvent

_log = logging.getLogger(__name__)

_CHAT_PATH = "/v1/chat/completions"


def _raise_for_status(response: httpx.Response) -> None:
    status = response.status_code
    if status == 400:
        raise ProviderValidationError(f"DeepSeek 400: {status}")
    if status in (401, 403):
        raise ProviderAuthError(f"DeepSeek auth error: {status}")
    if status == 429:
        raise ProviderRateLimitError("DeepSeek rate limit")
    if 500 <= status < 600:
        raise ProviderServerError(f"DeepSeek server error: {status}")
    if 400 <= status < 500:
        raise ProviderClientError(f"DeepSeek client error: {status}")


def _build_payload(request: ModelCallRequest, spec: ModelSpec, stream: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": spec.provider_model_id,
        "messages": request.messages,
        "stream": stream,
    }
    if request.max_tokens is not None:
        payload["max_tokens"] = request.max_tokens
    if request.temperature is not None:
        payload["temperature"] = request.temperature
    if request.tools:
        payload["tools"] = [t.model_dump() for t in request.tools]
        payload["tool_choice"] = "auto"
    if request.response_schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "output", "schema": request.response_schema},
        }
    if stream:
        payload["stream_options"] = {"include_usage": True}
    return payload


def _parse_tool_calls(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": tc.get("id", ""),
            "type": tc.get("type", "function"),
            "function": {
                "name": tc.get("function", {}).get("name", ""),
                "arguments": tc.get("function", {}).get("arguments", ""),
            },
        }
        for tc in raw
    ]


class DeepSeekAdapter(BaseProviderAdapter):
    def __init__(self, api_key: str, base_url: str, timeout: float) -> None:
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def execute(self, request: ModelCallRequest, spec: ModelSpec) -> ModelCallResponse:
        payload = _build_payload(request, spec, stream=False)
        url = f"{self._base_url}{_CHAT_PATH}"

        response = self._client.post(url, headers=self._headers, json=payload)
        _raise_for_status(response)

        data = response.json()
        choice = data["choices"][0]
        message = choice["message"]
        raw_usage = data.get("usage", {})

        content = message.get("content") or ""

        if request.response_schema is not None:
            try:
                parsed = json.loads(content)
            except (json.JSONDecodeError, ValueError) as exc:
                raise ProviderValidationError(
                    "structured output is not valid JSON"
                ) from exc
            try:
                jsonschema.validate(instance=parsed, schema=request.response_schema)
            except jsonschema.exceptions.ValidationError as exc:
                raise ProviderValidationError(
                    f"structured output failed schema validation: {exc.message}"
                ) from exc

        return ModelCallResponse(
            model_id=request.model_id,
            provider=spec.provider,
            provider_model_id=spec.provider_model_id,
            content=content,
            tool_calls=_parse_tool_calls(message.get("tool_calls") or []),
            usage=UsageSummary(
                input_tokens=raw_usage.get("prompt_tokens", 0),
                output_tokens=raw_usage.get("completion_tokens", 0),
                cache_read_tokens=raw_usage.get("prompt_cache_hit_tokens", 0),
                cache_write_tokens=raw_usage.get("prompt_cache_miss_tokens", 0),
            ),
            finish_reason=choice.get("finish_reason") or "unknown",
        )

    def stream(self, request: ModelCallRequest, spec: ModelSpec) -> Iterator[StreamingEvent]:
        payload = _build_payload(request, spec, stream=True)
        url = f"{self._base_url}{_CHAT_PATH}"

        with self._client.stream("POST", url, headers=self._headers, json=payload) as response:
            try:
                _raise_for_status(response)
            except Exception as exc:
                yield StreamError(code=type(exc).__name__, message="provider error")
                return

            for line in response.iter_lines():
                for event in parse_sse_line(line):
                    yield event
