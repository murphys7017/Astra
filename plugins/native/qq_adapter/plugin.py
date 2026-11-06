"""Native OneBot 11 adapter for the first real message path."""

from collections.abc import Mapping
import asyncio
import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from astra import CapabilitySpec, Component, Invocation, PluginConfigSchema, SideEffect


def _resolve_secret(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Mapping):
        reference = value.get("ref")
        if isinstance(reference, str) and reference.startswith("env:"):
            return os.environ.get(reference[4:], "")
        return ""
    return str(value)


def _validate_config(config: Mapping[str, Any]) -> Mapping[str, Any]:
    component_name = config.get("component_name", "qq.adapter")
    if not isinstance(component_name, str) or not component_name.strip():
        raise ValueError("component_name must be a non-empty string")
    api_url = config.get("api_url", "")
    if not isinstance(api_url, str):
        raise ValueError("api_url must be a string")
    dry_run = config.get("dry_run", False)
    if not isinstance(dry_run, bool):
        raise ValueError("dry_run must be boolean")
    if not dry_run and not api_url.strip():
        raise ValueError("api_url is required when dry_run is false")
    send_action = config.get("send_action", "send_msg")
    if not isinstance(send_action, str) or not send_action.strip():
        raise ValueError("send_action must be a non-empty string")
    access_token = config.get("access_token", {})
    if not isinstance(access_token, Mapping):
        raise ValueError("access_token must be an environment reference object")
    reference = access_token.get("ref")
    if reference is not None and (
        not isinstance(reference, str) or not reference.startswith("env:")
    ):
        raise ValueError("access_token.ref must use env: prefix")
    listen_enabled = config.get("listen_enabled", False)
    if not isinstance(listen_enabled, bool):
        raise ValueError("listen_enabled must be boolean")
    listen_host = config.get("listen_host", "127.0.0.1")
    if not isinstance(listen_host, str) or not listen_host.strip():
        raise ValueError("listen_host must be a non-empty string")
    listen_port = config.get("listen_port", 12398)
    if isinstance(listen_port, bool) or not isinstance(listen_port, int) or not 0 <= listen_port <= 65535:
        raise ValueError("listen_port must be between 0 and 65535")
    workflow_name = config.get("workflow_name", "")
    if not isinstance(workflow_name, str):
        raise ValueError("workflow_name must be a string")
    return {
        "component_name": component_name.strip(),
        "api_url": api_url.rstrip("/"),
        "dry_run": dry_run,
        "send_action": send_action.strip(),
        "access_token": dict(access_token),
        "listen_enabled": listen_enabled,
        "listen_host": listen_host.strip(),
        "listen_port": listen_port,
        "workflow_name": workflow_name.strip(),
    }


def create_config_schema() -> PluginConfigSchema:
    return PluginConfigSchema(
        version=1,
        defaults={
            "component_name": "qq.adapter",
            "api_url": "",
            "dry_run": False,
            "send_action": "send_msg",
            "access_token": {},
            "listen_enabled": False,
            "listen_host": "127.0.0.1",
            "listen_port": 12398,
            "workflow_name": "",
        },
        validator=_validate_config,
    )


def _extract_text(message: Any) -> str:
    if isinstance(message, str):
        return message
    if not isinstance(message, list):
        return ""
    parts = []
    for segment in message:
        if not isinstance(segment, Mapping):
            continue
        if segment.get("type") == "text":
            data = segment.get("data", {})
            if isinstance(data, Mapping):
                parts.append(str(data.get("text") or ""))
    return "".join(parts)


def _normalize_event(event: Any) -> Mapping[str, Any]:
    if not isinstance(event, Mapping):
        raise TypeError("QQ event must be an object")
    if event.get("post_type", "message") != "message":
        raise ValueError("QQ event must be a message event")
    message_type = event.get("message_type")
    if message_type not in {"private", "group"}:
        raise ValueError("QQ message_type must be private or group")
    message = event.get("message")
    if message is None:
        message = event.get("raw_message", "")
    text = _extract_text(message).strip()
    if not text:
        raise ValueError("QQ message contains no text")
    sender = event.get("sender", {})
    if not isinstance(sender, Mapping):
        sender = {}
    user_id = str(event.get("user_id") or sender.get("user_id") or "").strip()
    group_id = str(event.get("group_id") or "").strip()
    if not user_id:
        raise ValueError("QQ message user_id is required")
    if message_type == "group" and not group_id:
        raise ValueError("QQ group message group_id is required")
    conversation_id = group_id if message_type == "group" else user_id
    return {
        "platform": "qq",
        "message_id": str(event.get("message_id") or "").strip(),
        "conversation_id": conversation_id,
        "text": text,
        "sender": {
            "user_id": user_id,
            "nickname": str(sender.get("nickname") or "").strip(),
        },
        "reply_target": {
            "message_type": message_type,
            "user_id": user_id,
            "group_id": group_id,
        },
        "metadata": {
            "sub_type": str(event.get("sub_type") or "").strip(),
        },
    }


def _send_request(url: str, token: str, body: Mapping[str, Any], timeout: float) -> Mapping[str, Any]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(
        url,
        data=json.dumps(dict(body), ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("QQ send request failed") from exc
    if not isinstance(payload, Mapping):
        raise RuntimeError("QQ send response must be an object")
    if payload.get("status") == "failed" or payload.get("retcode", 0) != 0:
        raise RuntimeError("QQ send request was rejected")
    return payload


class QQAdapterComponent(Component):
    def __init__(self, config: Mapping[str, Any]) -> None:
        super().__init__(str(config["component_name"]))
        self._api_url = str(config["api_url"])
        self._dry_run = bool(config["dry_run"])
        self._send_action = str(config["send_action"])
        self._token = _resolve_secret(config.get("access_token"))
        self._listen_enabled = bool(config["listen_enabled"])
        self._listen_host = str(config["listen_host"])
        self._listen_port = int(config["listen_port"])
        self._workflow_name = str(config["workflow_name"])
        self._runtime = None
        self._server: asyncio.AbstractServer | None = None

    @property
    def capabilities(self):
        return (
            CapabilitySpec(
                "qq.message.receive",
                version="1",
                input_type="onebot11.event",
                output_type="astra.message",
            ),
            CapabilitySpec(
                "qq.message.send",
                version="1",
                side_effect=SideEffect.EXTERNAL_EFFECT,
                permissions=frozenset({"network.qq"}),
                input_type="astra.reply",
                output_type="onebot11.result",
            ),
        )

    async def start(self, runtime) -> None:
        self._runtime = runtime
        if not self._listen_enabled:
            return
        if not self._workflow_name:
            raise ValueError("workflow_name is required when listen_enabled is true")
        self._server = await asyncio.start_server(
            self._handle_connection,
            self._listen_host,
            self._listen_port,
        )

    async def stop(self) -> None:
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None

    @property
    def listen_address(self) -> tuple[str, int] | None:
        if self._server is None or not self._server.sockets:
            return None
        address = self._server.sockets[0].getsockname()
        return str(address[0]), int(address[1])

    async def invoke(self, capability: str, request: Any, invocation: Invocation) -> Any:
        invocation.raise_if_cancelled()
        if capability == "qq.message.receive":
            return _normalize_event(request)
        if capability == "qq.message.send":
            return await self._send(request)
        raise KeyError("unknown QQ capability: {}".format(capability))

    async def _send(self, request: Any) -> Mapping[str, Any]:
        if not isinstance(request, Mapping):
            raise TypeError("QQ send request must be an object")
        text = request.get("text")
        target = request.get("target")
        if not isinstance(text, str) or not text.strip():
            raise TypeError("QQ send text must be a non-empty string")
        if not isinstance(target, Mapping):
            raise TypeError("QQ send target must be an object")
        body = dict(target)
        body["message"] = text
        if self._dry_run:
            return {"sent": False, "dry_run": True, "request": body}
        payload = await asyncio.to_thread(
            _send_request,
            self._api_url + "/" + self._send_action,
            self._token,
            body,
            30.0,
        )
        return {"sent": True, "dry_run": False, "response": dict(payload)}

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            header_bytes = await reader.readuntil(b"\r\n\r\n")
            header_text = header_bytes.decode("iso-8859-1")
            headers = {}
            for line in header_text.split("\r\n")[1:]:
                if ":" in line:
                    key, value = line.split(":", 1)
                    headers[key.lower().strip()] = value.strip()
            content_length = int(headers.get("content-length", "0"))
            if content_length < 0 or content_length > 1_048_576:
                raise ValueError("invalid QQ request body size")
            body = await reader.readexactly(content_length)
            event = json.loads(body.decode("utf-8"))
            if self._runtime is None:
                raise RuntimeError("QQ adapter runtime is not started")
            result = await self._runtime.run_workflow(self._workflow_name, event)
            await self._write_http_response(writer, 200, {"status": "ok", "data": result})
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, ValueError, json.JSONDecodeError):
            await self._write_http_response(writer, 400, {"status": "failed", "message": "invalid QQ event"})
        except Exception:
            await self._write_http_response(writer, 500, {"status": "failed", "message": "QQ workflow failed"})
        finally:
            writer.close()
            await writer.wait_closed()

    @staticmethod
    async def _write_http_response(
        writer: asyncio.StreamWriter,
        status: int,
        payload: Mapping[str, Any],
    ) -> None:
        encoded = json.dumps(dict(payload), ensure_ascii=False).encode("utf-8")
        reason = "OK" if status == 200 else "Bad Request" if status == 400 else "Internal Server Error"
        writer.write(
            (
                "HTTP/1.1 {} {}\r\n"
                "Content-Type: application/json\r\n"
                "Content-Length: {}\r\n"
                "Connection: close\r\n\r\n"
            ).format(status, reason, len(encoded)).encode("ascii") + encoded
        )
        await writer.drain()


def create_components(config: Mapping[str, Any]):
    return QQAdapterComponent(config)
