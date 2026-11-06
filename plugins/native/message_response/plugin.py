"""First native message response slice for the Astra migration."""

from collections.abc import Mapping
import re
from typing import Any

from astra import CapabilitySpec, FunctionComponent, PluginConfigSchema


_SYSTEM_REMINDER_PATTERN = re.compile(
    r"<system_reminder>[\s\S]*?</system_reminder>",
    re.IGNORECASE,
)


def _validate_config(config: Mapping[str, Any]) -> Mapping[str, Any]:
    prefix = config.get("prefix", "")
    if not isinstance(prefix, str):
        raise ValueError("prefix must be a string")
    mode = config.get("mode", "echo")
    if mode != "echo":
        raise ValueError("mode must be echo")
    return {"prefix": prefix, "mode": mode}


def create_config_schema() -> PluginConfigSchema:
    return PluginConfigSchema(
        version=1,
        defaults={"prefix": "", "mode": "echo"},
        validator=_validate_config,
    )


def _sanitize_text(value: str) -> str:
    text = _SYSTEM_REMINDER_PATTERN.sub("", value)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _respond(request: Any, _invocation: Any, *, prefix: str) -> Mapping[str, Any]:
    if isinstance(request, str):
        text = request
        metadata = {}
    elif isinstance(request, Mapping):
        text = request.get("text")
        metadata = request.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise TypeError("message metadata must be an object")
    else:
        raise TypeError("message request must be a string or object")
    if not isinstance(text, str):
        raise TypeError("message text must be a string")
    return {
        "text": prefix + _sanitize_text(text),
        "metadata": dict(metadata),
    }


def create_components(config: Mapping[str, Any]):
    prefix = str(config["prefix"])
    handler = lambda request, invocation: _respond(
        request,
        invocation,
        prefix=prefix,
    )
    return [
        FunctionComponent(
            "native.message-response",
            {"message.respond": handler},
            capabilities={
                "message.respond": CapabilitySpec("message.respond", version="1")
            },
        )
    ]
