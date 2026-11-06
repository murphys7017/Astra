"""Run the first native plugin message-response slice."""

import argparse
import asyncio
import json
from pathlib import Path
import sys
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from astra import (
    MemoryLogSink,
    PluginLoader,
    Runtime,
    RuntimeConfig,
    SerialWorkflow,
    StructuredLogger,
)


async def respond(message: str) -> dict[str, Any]:
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
    PluginLoader(REPOSITORY_ROOT / "plugins").load_configured(runtime, config)
    runtime.register_workflow(
        SerialWorkflow(
            "message-response",
            [lambda context, value: context.invoke("message.respond", value)],
        )
    )
    runtime.apply_config(config)
    await runtime.start()
    try:
        result = await runtime.run_workflow("message-response", {"text": message})
        return dict(result)
    finally:
        await runtime.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("message", help="message text to send through the native workflow")
    args = parser.parse_args()
    result = asyncio.run(respond(args.message))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
