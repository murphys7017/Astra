"""Run the first real QQ -> Personal -> LLM -> QQ message workflow."""

import argparse
import asyncio
import json
from pathlib import Path
import sys
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from astra import (  # noqa: E402
    MemoryLogSink,
    PluginLoader,
    Runtime,
    RuntimeConfig,
    SerialWorkflow,
    StructuredLogger,
)


def _default_model(provider: str) -> str:
    return "deepseek-chat" if provider == "deepseek" else "MiniMax-Text-01"


def _default_endpoint(provider: str) -> str:
    if provider == "deepseek":
        return "https://api.deepseek.com/chat/completions"
    return "https://api.minimaxi.com/v1/chat/completions"


async def respond(
    event: dict[str, Any],
    *,
    provider: str,
    model: str,
    endpoint: str,
    api_key_env: str,
    qq_api_url: str,
    qq_access_token_env: str,
    system_prompt: str,
    dry_run: bool,
) -> dict[str, Any]:
    runtime = Runtime(StructuredLogger([MemoryLogSink()]))
    config = RuntimeConfig.from_dict(
        {
            "plugins": {
                "instances": {
                    "native-qq-adapter": {
                        "config": {
                            "api_url": qq_api_url,
                            "dry_run": dry_run,
                            "access_token": {"ref": "env:" + qq_access_token_env},
                            "workflow_name": "qq-personal-response",
                        }
                    },
                    "native-model-providers": {
                        "config": {
                            "providers": {
                                provider: {
                                    "enabled": True,
                                    "endpoint": endpoint,
                                    "model": model,
                                    "api_key": {"ref": "env:" + api_key_env},
                                }
                            }
                        }
                    },
                    "native-personal-response": {
                        "config": {"system_prompt": system_prompt}
                    },
                }
            },
            "components": [
                "qq.adapter",
                "llm." + provider,
                "personal.response",
                "workflow:qq-personal-response",
            ],
            "workflows": [{"name": "qq-personal-response"}],
            "bindings": {
                "qq.message.receive": {
                    "provider": "qq.adapter",
                    "version": "1",
                },
                "personal.respond": {
                    "provider": "personal.response",
                    "version": "1",
                },
                "llm.generate": {
                    "provider": "llm." + provider,
                    "version": "1",
                },
                "qq.message.send": {
                    "provider": "qq.adapter",
                    "version": "1",
                },
            },
            "permissions": {"allow": ["network.qq", "network.llm"]},
        }
    )
    PluginLoader(REPOSITORY_ROOT / "plugins").load_configured(runtime, config)

    async def deliver(context, value):
        delivery = await context.invoke(
            "qq.message.send",
            {"text": value["text"], "target": value["target"]},
        )
        return {"reply": value, "delivery": delivery}

    runtime.register_workflow(
        SerialWorkflow(
            "qq-personal-response",
            [
                lambda context, value: context.invoke("qq.message.receive", value),
                lambda context, value: context.invoke("personal.respond", value),
                deliver,
            ],
        )
    )
    runtime.apply_config(config)
    await runtime.start()
    try:
        result = await runtime.run_workflow("qq-personal-response", event)
        return dict(result)
    finally:
        await runtime.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("message", help="message text received from QQ")
    parser.add_argument("--provider", choices=("deepseek", "minimax"), default="deepseek")
    parser.add_argument("--model", default=None)
    parser.add_argument("--endpoint", default=None)
    parser.add_argument("--api-key-env", default="ASTRA_LLM_API_KEY")
    parser.add_argument("--qq-api-url", default="")
    parser.add_argument("--qq-access-token-env", default="ASTRA_QQ_ACCESS_TOKEN")
    parser.add_argument("--system-prompt", default="You are a helpful assistant. Answer the user directly and clearly.")
    parser.add_argument("--user-id", default="astra-user")
    parser.add_argument("--group-id", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    message_type = "group" if args.group_id else "private"
    event = {
        "post_type": "message",
        "message_type": message_type,
        "message_id": "cli-message",
        "user_id": args.user_id,
        "group_id": args.group_id,
        "message": args.message,
        "sender": {"user_id": args.user_id, "nickname": "Astra User"},
    }
    result = asyncio.run(
        respond(
            event,
            provider=args.provider,
            model=args.model or _default_model(args.provider),
            endpoint=args.endpoint or _default_endpoint(args.provider),
            api_key_env=args.api_key_env,
            qq_api_url=args.qq_api_url,
            qq_access_token_env=args.qq_access_token_env,
            system_prompt=args.system_prompt,
            dry_run=args.dry_run or not args.qq_api_url,
        )
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
