"""OpenAI-compatible DeepSeek and MiniMax provider components."""

from collections.abc import Mapping
import asyncio
import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from astra import CapabilitySpec, FunctionComponent, PluginConfigSchema, SideEffect


_DEFAULT_ENDPOINTS = {
    "deepseek": "https://api.deepseek.com/chat/completions",
    "minimax": "https://api.minimaxi.com/v1/chat/completions",
}


def _resolve_secret(value: Any) -> str:
    if not isinstance(value, Mapping):
        return ""
    reference = value.get("ref")
    if isinstance(reference, str) and reference.startswith("env:"):
        return os.environ.get(reference[4:], "")
    return ""


def _validate_provider(name: str, raw: Any) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError("provider {} must be an object".format(name))
    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("provider {}.enabled must be boolean".format(name))
    component_name = raw.get("component_name", "llm." + name)
    if not isinstance(component_name, str) or not component_name.strip():
        raise ValueError("provider {}.component_name must be a non-empty string".format(name))
    endpoint = raw.get("endpoint", _DEFAULT_ENDPOINTS.get(name, ""))
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise ValueError("provider {}.endpoint must be a non-empty string".format(name))
    model = raw.get("model", "")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("provider {}.model must be a non-empty string".format(name))
    api_key = raw.get("api_key", {})
    if not isinstance(api_key, Mapping):
        raise ValueError("provider {}.api_key must be an environment reference object".format(name))
    reference = api_key.get("ref")
    if not isinstance(reference, str) or not reference.startswith("env:"):
        raise ValueError("provider {}.api_key.ref must use env: prefix".format(name))
    timeout = raw.get("timeout_seconds", 60.0)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("provider {}.timeout_seconds must be positive".format(name))
    temperature = raw.get("temperature", 0.7)
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
        raise ValueError("provider {}.temperature must be numeric".format(name))
    max_tokens = raw.get("max_tokens")
    if max_tokens is not None and (
        isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens < 1
    ):
        raise ValueError("provider {}.max_tokens must be positive".format(name))
    return {
        "enabled": enabled,
        "component_name": component_name.strip(),
        "endpoint": endpoint.strip(),
        "model": model.strip(),
        "api_key": dict(api_key),
        "timeout_seconds": float(timeout),
        "temperature": float(temperature),
        "max_tokens": max_tokens,
    }


def _validate_config(config: Mapping[str, Any]) -> Mapping[str, Any]:
    providers = config.get("providers", {})
    if not isinstance(providers, Mapping) or not providers:
        raise ValueError("providers must contain at least one provider")
    resolved = {}
    for name, raw in providers.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("provider name must be a non-empty string")
        resolved[name.strip()] = _validate_provider(name.strip(), raw)
    if not any(item["enabled"] for item in resolved.values()):
        raise ValueError("at least one model provider must be enabled")
    return {"providers": resolved}


def create_config_schema() -> PluginConfigSchema:
    return PluginConfigSchema(version=1, defaults={"providers": {}}, validator=_validate_config)


def _extract_text(payload: Mapping[str, Any]) -> str:
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, Mapping):
            message = first.get("message")
            if isinstance(message, Mapping) and isinstance(message.get("content"), str):
                return message["content"]
            if isinstance(first.get("text"), str):
                return first["text"]
    reply = payload.get("reply")
    if isinstance(reply, str):
        return reply
    raise RuntimeError("model response contains no text")


def _request_completion(
    endpoint: str,
    token: str,
    model: str,
    messages: list[Mapping[str, Any]],
    temperature: float,
    max_tokens: int | None,
    timeout: float,
) -> Mapping[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens is not None:
        body["max_tokens"] = max_tokens
    request = Request(
        endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("model provider request failed") from exc
    if not isinstance(payload, Mapping):
        raise RuntimeError("model provider response must be an object")
    return payload


def create_components(config: Mapping[str, Any]):
    components = []
    for provider_name, raw in config["providers"].items():
        if not raw["enabled"]:
            continue
        component_name = str(raw["component_name"])
        endpoint = str(raw["endpoint"])
        model = str(raw["model"])
        token = _resolve_secret(raw["api_key"])
        timeout = float(raw["timeout_seconds"])
        temperature = float(raw["temperature"])
        max_tokens = raw["max_tokens"]

        async def generate(
            request: Any,
            _invocation: Any,
            *,
            _provider_name=provider_name,
            _endpoint=endpoint,
            _model=model,
            _token=token,
            _timeout=timeout,
            _temperature=temperature,
            _max_tokens=max_tokens,
        ) -> Mapping[str, Any]:
            if not _token:
                raise RuntimeError("model provider API key is not configured")
            if not isinstance(request, Mapping):
                raise TypeError("llm request must be an object")
            messages = request.get("messages")
            if not isinstance(messages, list) or not messages:
                raise TypeError("llm request messages must be a non-empty array")
            normalized_messages = []
            for message in messages:
                if not isinstance(message, Mapping):
                    raise TypeError("llm messages must contain objects")
                role = message.get("role")
                content = message.get("content")
                if not isinstance(role, str) or not isinstance(content, str):
                    raise TypeError("llm message role and content must be strings")
                normalized_messages.append({"role": role, "content": content})
            payload = await asyncio.to_thread(
                _request_completion,
                _endpoint,
                _token,
                str(request.get("model") or _model),
                normalized_messages,
                float(request.get("temperature", _temperature)),
                request.get("max_tokens", _max_tokens),
                _timeout,
            )
            return {
                "text": _extract_text(payload),
                "provider": _provider_name,
                "model": str(request.get("model") or _model),
                "usage": dict(payload.get("usage", {}))
                if isinstance(payload.get("usage"), Mapping)
                else {},
            }

        components.append(
            FunctionComponent(
                component_name,
                {"llm.generate": generate},
                capabilities={
                    "llm.generate": CapabilitySpec(
                        "llm.generate",
                        version="1",
                        side_effect=SideEffect.EXTERNAL_EFFECT,
                        permissions=frozenset({"network.llm"}),
                        input_type="llm.request",
                        output_type="llm.response",
                    )
                },
            )
        )
    return components
