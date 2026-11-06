"""Minimal Personal response component backed by the configured LLM provider."""

from collections.abc import Mapping
from typing import Any

from astra import CapabilitySpec, FunctionComponent, PluginConfigSchema


def _validate_config(config: Mapping[str, Any]) -> Mapping[str, Any]:
    system_prompt = config.get(
        "system_prompt",
        "You are a helpful assistant. Answer the user directly and clearly.",
    )
    if not isinstance(system_prompt, str) or not system_prompt.strip():
        raise ValueError("system_prompt must be a non-empty string")
    max_history = config.get("max_history", 8)
    if isinstance(max_history, bool) or not isinstance(max_history, int) or max_history < 0:
        raise ValueError("max_history must be a non-negative integer")
    return {
        "system_prompt": system_prompt,
        "max_history": max_history,
    }


def create_config_schema() -> PluginConfigSchema:
    return PluginConfigSchema(
        version=1,
        defaults={
            "system_prompt": "You are a helpful assistant. Answer the user directly and clearly.",
            "max_history": 8,
        },
        validator=_validate_config,
    )


def _history_messages(raw_history: Any, max_history: int) -> list[dict[str, str]]:
    if raw_history is None:
        return []
    if not isinstance(raw_history, list):
        raise TypeError("personal history must be an array")
    messages = []
    for item in raw_history[-max_history:]:
        if not isinstance(item, Mapping):
            raise TypeError("personal history items must be objects")
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str):
            raise TypeError("personal history items must contain a valid role and content")
        messages.append({"role": role, "content": content})
    return messages


def create_components(config: Mapping[str, Any]):
    system_prompt = str(config["system_prompt"])
    max_history = int(config["max_history"])

    async def respond(request: Any, invocation: Any) -> Mapping[str, Any]:
        if not isinstance(request, Mapping):
            raise TypeError("personal request must be an object")
        text = request.get("text")
        if not isinstance(text, str) or not text.strip():
            raise TypeError("personal request text must be a non-empty string")
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(_history_messages(request.get("history"), max_history))
        messages.append({"role": "user", "content": text})
        result = await invocation.run.runtime.invoke(
            "llm.generate",
            {"messages": messages},
            run=invocation.run,
        )
        if not isinstance(result, Mapping) or not isinstance(result.get("text"), str):
            raise RuntimeError("llm response does not contain text")
        return {
            "text": result["text"].strip(),
            "target": dict(request.get("reply_target", {}))
            if isinstance(request.get("reply_target"), Mapping)
            else {},
            "conversation_id": str(request.get("conversation_id") or ""),
            "metadata": {
                "provider": result.get("provider", ""),
                "model": result.get("model", ""),
                "usage": dict(result.get("usage", {}))
                if isinstance(result.get("usage"), Mapping)
                else {},
            },
        }

    return FunctionComponent(
        "personal.response",
        {"personal.respond": respond},
        capabilities={
            "personal.respond": CapabilitySpec(
                "personal.respond",
                version="1",
                input_type="astra.message",
                output_type="astra.reply",
            )
        },
    )
