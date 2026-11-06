import asyncio
from pathlib import Path
import unittest

from astra import (
    MemoryLogSink,
    PluginLoader,
    Runtime,
    RuntimeConfig,
    SerialWorkflow,
    StructuredLogger,
)


ROOT = Path(__file__).resolve().parents[1]


class NativeMessagePluginTests(unittest.TestCase):
    def test_native_message_response_plugin_runs_through_workflow(self):
        async def scenario():
            runtime = Runtime(StructuredLogger([MemoryLogSink()]))
            config = RuntimeConfig.from_dict(
                {
                    "plugins": {
                        "instances": {
                            "native-message-response": {
                                "config": {"prefix": "Astra: "}
                            }
                        }
                    },
                    "components": [
                        "native.message-response",
                        "workflow:message-response",
                    ],
                    "workflows": [{"name": "message-response"}],
                    "bindings": {
                        "message.respond": {
                            "provider": "native.message-response",
                            "version": "1",
                        }
                    },
                }
            )
            PluginLoader(ROOT / "plugins").load_configured(runtime, config)
            runtime.register_workflow(
                SerialWorkflow(
                    "message-response",
                    [lambda context, value: context.invoke("message.respond", value)],
                )
            )
            runtime.apply_config(config)
            await runtime.start()
            try:
                result = await runtime.run_workflow(
                    "message-response",
                    {"text": "hello <system_reminder>private</system_reminder>"},
                )
                self.assertEqual(result, {"text": "Astra: hello", "metadata": {}})
            finally:
                await runtime.stop()

        asyncio.run(scenario())
