import asyncio
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
from threading import Thread
from urllib.request import Request, urlopen
import unittest

from astra import MemoryLogSink, PluginLoader, Runtime, RuntimeConfig, SerialWorkflow, StructuredLogger
from tools.run_qq_personal import respond


ROOT = Path(__file__).resolve().parents[1]


class _ProviderAndQQHandler(BaseHTTPRequestHandler):
    requests = []

    def do_POST(self):  # noqa: N802 - stdlib handler API
        size = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(size).decode("utf-8"))
        self.requests.append((self.path, body))
        if self.path.endswith("/chat/completions"):
            payload = {
                "choices": [{"message": {"content": "来自模型的真实响应"}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 6},
            }
        elif self.path.endswith("/send_msg"):
            payload = {"status": "ok", "retcode": 0, "data": {"message_id": 9}}
        else:
            self.send_response(404)
            self.end_headers()
            return
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_args):
        return


class NativeQQPersonalFlowTests(unittest.TestCase):
    def test_qq_message_reaches_model_and_is_sent_back(self):
        _ProviderAndQQHandler.requests = []
        server = ThreadingHTTPServer(("127.0.0.1", 0), _ProviderAndQQHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        os.environ["ASTRA_TEST_MODEL_KEY"] = "model-key"
        os.environ["ASTRA_TEST_QQ_TOKEN"] = "qq-token"
        base_url = "http://127.0.0.1:{}".format(server.server_port)
        event = {
            "post_type": "message",
            "message_type": "group",
            "message_id": "qq-1",
            "user_id": "10001",
            "group_id": "20002",
            "message": [{"type": "text", "data": {"text": "你好"}}],
            "sender": {"user_id": "10001", "nickname": "测试用户"},
        }
        try:
            result = asyncio.run(
                respond(
                    event,
                    provider="deepseek",
                    model="deepseek-chat",
                    endpoint=base_url + "/chat/completions",
                    api_key_env="ASTRA_TEST_MODEL_KEY",
                    qq_api_url=base_url,
                    qq_access_token_env="ASTRA_TEST_QQ_TOKEN",
                    system_prompt="你是 Astra 的个人响应模块。",
                    dry_run=False,
                )
            )
        finally:
            server.shutdown()
            server.server_close()
            os.environ.pop("ASTRA_TEST_MODEL_KEY", None)
            os.environ.pop("ASTRA_TEST_QQ_TOKEN", None)

        self.assertEqual(result["reply"]["text"], "来自模型的真实响应")
        self.assertTrue(result["delivery"]["sent"])
        self.assertEqual(
            [path for path, _body in _ProviderAndQQHandler.requests],
            ["/chat/completions", "/send_msg"],
        )
        model_request = _ProviderAndQQHandler.requests[0][1]
        self.assertEqual(model_request["messages"][0]["content"], "你是 Astra 的个人响应模块。")
        self.assertEqual(model_request["messages"][-1]["content"], "你好")
        send_request = _ProviderAndQQHandler.requests[1][1]
        self.assertEqual(send_request["group_id"], "20002")
        self.assertEqual(send_request["message"], "来自模型的真实响应")

    def test_qq_http_ingress_triggers_a_workflow(self):
        async def scenario():
            runtime = Runtime(StructuredLogger([MemoryLogSink()]))
            config = RuntimeConfig.from_dict(
                {
                    "plugins": {
                        "instances": {
                            "native-qq-adapter": {
                                "config": {
                                    "dry_run": True,
                                    "listen_enabled": True,
                                    "listen_port": 0,
                                    "workflow_name": "receive-only",
                                }
                            }
                        }
                    },
                    "components": ["qq.adapter", "workflow:receive-only"],
                    "workflows": [{"name": "receive-only"}],
                    "bindings": {
                        "qq.message.receive": {
                            "provider": "qq.adapter",
                            "version": "1",
                        }
                    },
                }
            )
            loaded = PluginLoader(ROOT / "plugins").load_configured(runtime, config)
            runtime.register_workflow(
                SerialWorkflow(
                    "receive-only",
                    [lambda context, value: context.invoke("qq.message.receive", value)],
                )
            )
            runtime.apply_config(config)
            await runtime.start()
            try:
                adapter = loaded[0].components[0]
                address = adapter.listen_address
                self.assertIsNotNone(address)
                host, port = address
                event = {
                    "post_type": "message",
                    "message_type": "private",
                    "message_id": "qq-http-1",
                    "user_id": "10001",
                    "message": "通过 HTTP 接收",
                }
                request = Request(
                    "http://{}:{}/".format(host, port),
                    data=json.dumps(event, ensure_ascii=False).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                def send_request():
                    with urlopen(request, timeout=2) as response:
                        return json.loads(response.read().decode("utf-8"))

                payload = await asyncio.to_thread(send_request)
                self.assertEqual(payload["status"], "ok")
                self.assertEqual(payload["data"]["text"], "通过 HTTP 接收")
            finally:
                await runtime.stop()

        asyncio.run(scenario())
