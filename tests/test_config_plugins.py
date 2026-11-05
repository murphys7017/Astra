import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from astra import (
    CapabilityRequirement,
    CapabilitySpec,
    ChildWorkflow,
    ComponentLifecycleError,
    ConfigurationError,
    FunctionComponent,
    MemoryLogSink,
    PermissionDeniedError,
    PluginLoader,
    PluginDependencyError,
    Runtime,
    RuntimeConfig,
    SensitiveConfigurationError,
    SerialWorkflow,
    StructuredLogger,
)


class ConfigAndPluginTests(unittest.TestCase):
    def run_async(self, coroutine):
        return asyncio.run(coroutine)

    def test_json_config_creates_redacted_immutable_snapshot(self):
        config = RuntimeConfig.from_dict(
            {
                "schema_version": 1,
                "components": ["provider"],
                "workflows": [{"name": "main", "params": {"mode": "fast"}}],
                "bindings": {"echo": {"provider": "provider", "version": "1"}},
                "composition": {
                    "order": ["main"],
                    "parallel": [],
                    "branches": [],
                },
                "secrets": {"api_key": {"ref": "env:ASTRA_API_KEY"}},
            }
        )
        self.assertEqual(config.workflow_order, ("main",))
        self.assertEqual(config.secrets["api_key"].reference, "env:ASTRA_API_KEY")
        self.assertNotIn("ASTRA_API_KEY", str(config.redacted()))

        async def scenario():
            runtime = Runtime(StructuredLogger([MemoryLogSink()]))
            runtime.register_component(FunctionComponent("provider", {"echo": lambda request, inv: request}))
            runtime.register_workflow(
                SerialWorkflow("main", [lambda context, value: context.params["mode"] + ":" + value])
            )
            runtime.apply_config(config)
            self.assertEqual(runtime.composition.generation, 1)
            await runtime.start()
            self.assertEqual(await runtime.run_workflow("main", "ok"), "fast:ok")
            await runtime.stop()

        self.run_async(scenario())

    def test_unsafe_secret_shapes_are_rejected(self):
        with self.assertRaises(SensitiveConfigurationError):
            RuntimeConfig.from_dict({"api_key": "raw"})
        with self.assertRaises(SensitiveConfigurationError):
            RuntimeConfig.from_dict({"secrets": {"api_key": {"value": "raw", "protected": False}}})
        with self.assertRaises(ConfigurationError):
            RuntimeConfig.from_dict({"unknown": True})
        with self.assertRaises(ConfigurationError):
            RuntimeConfig.from_dict({"components": ["same", "same"]})
        with self.assertRaises(ConfigurationError):
            RuntimeConfig.from_dict({"schema_version": True})
        with self.assertRaises(ConfigurationError):
            RuntimeConfig.from_dict({"workflows": [{"name": "same"}, {"name": "same", "enabled": False}]})
        with self.assertRaises(SensitiveConfigurationError):
            RuntimeConfig.from_dict({"permissions": {"secrets": {"api_key": "raw"}}})
        inline = RuntimeConfig.from_dict(
            {"secrets": {"api_key": {"value": "TOP-SECRET", "protected": True}}}
        )
        self.assertNotIn("TOP-SECRET", repr(inline))

    def test_composition_shape_is_rejected_before_runtime_start(self):
        with self.assertRaises(ConfigurationError):
            RuntimeConfig.from_dict({"composition": {"order": ["same", "same"]}})
        with self.assertRaises(ConfigurationError):
            RuntimeConfig.from_dict({"composition": {"parallel": [["left", "left"]]}})
        with self.assertRaises(ConfigurationError):
            RuntimeConfig.from_dict({"composition": {"parallel": [["left"]]}})
        with self.assertRaises(ConfigurationError):
            RuntimeConfig.from_dict({"composition": {"branches": [{"from": "left"}]}})
        with self.assertRaises(ConfigurationError):
            RuntimeConfig.from_dict(
                {"composition": {"branches": [{"from": "left", "to": "right"}, {"from": "left", "to": "end"}]}}
            )
        with self.assertRaises(ConfigurationError):
            RuntimeConfig.from_dict(
                {"composition": {"branches": [{"from": "left", "to": "right"}, {"from": "right", "to": "left"}]}}
            )

    def test_json_composition_executes_order_parallel_and_branch(self):
        async def scenario():
            runtime = Runtime(StructuredLogger([MemoryLogSink()]))
            runtime.register_workflow(SerialWorkflow("first", [lambda context, value: value + 1]))
            runtime.register_workflow(SerialWorkflow("second", [lambda context, value: value * 2]))
            runtime.apply_config(
                RuntimeConfig.from_dict(
                    {
                        "workflows": [{"name": "first"}, {"name": "second"}],
                        "composition": {"order": ["first", "second"]},
                    }
                )
            )
            await runtime.start()
            self.assertIs(runtime.build_composed_workflow(), runtime.build_composed_workflow())
            self.assertEqual(await runtime.run_composition(3), 8)
            await runtime.stop()

            runtime = Runtime(StructuredLogger([MemoryLogSink()]))
            runtime.register_workflow(SerialWorkflow("left", [lambda context, value: value + 10]))
            runtime.register_workflow(SerialWorkflow("right", [lambda context, value: value + 20]))
            runtime.register_workflow(SerialWorkflow("collect", [lambda context, value: sum(value)]))
            runtime.apply_config(
                RuntimeConfig.from_dict(
                    {
                        "workflows": [{"name": "left"}, {"name": "right"}, {"name": "collect"}],
                        "composition": {
                            "order": ["left", "right", "collect"],
                            "parallel": [["left", "right"]],
                        },
                    }
                )
            )
            await runtime.start()
            self.assertEqual(await runtime.run_composition(3), 36)
            await runtime.stop()

            runtime = Runtime(StructuredLogger([MemoryLogSink()]))
            runtime.register_workflow(SerialWorkflow("start", [lambda context, value: value + "-start"]))
            runtime.register_workflow(SerialWorkflow("finish", [lambda context, value: value + "-finish"]))
            runtime.apply_config(
                RuntimeConfig.from_dict(
                    {
                        "workflows": [{"name": "start"}, {"name": "finish"}],
                        "composition": {"branches": [{"from": "start", "to": "finish"}]},
                    }
                )
            )
            await runtime.start()
            self.assertEqual(await runtime.run_composition("value"), "value-start-finish")
            await runtime.stop()

        self.run_async(scenario())

    def test_composition_constraints_fail_during_config_apply(self):
        runtime = Runtime(StructuredLogger([MemoryLogSink()]))
        for name in ("first", "middle", "last"):
            runtime.register_workflow(SerialWorkflow(name, [lambda context, value: value]))
        with self.assertRaises(ConfigurationError):
            runtime.apply_config(
                RuntimeConfig.from_dict(
                    {
                        "workflows": [{"name": "first"}, {"name": "middle"}, {"name": "last"}],
                        "composition": {
                            "order": ["first", "last", "middle"],
                            "parallel": [["first", "middle"]],
                        },
                    }
                )
            )
        with self.assertRaises(ConfigurationError):
            runtime.apply_config(
                RuntimeConfig.from_dict(
                    {
                        "workflows": [{"name": "first"}, {"name": "middle"}],
                        "composition": {
                            "order": ["first", "middle"],
                            "branches": [{"from": "middle", "to": "first"}],
                        },
                    }
                )
            )
        with self.assertRaises(ConfigurationError):
            runtime.apply_config(
                RuntimeConfig.from_dict(
                    {
                        "workflows": [{"name": "first"}, {"name": "middle"}, {"name": "last"}],
                        "composition": {
                            "order": ["first"],
                            "branches": [{"from": "middle", "to": "last"}],
                        },
                    }
                )
            )

    def test_disabled_child_workflow_cannot_bypass_config(self):
        async def scenario():
            runtime = Runtime(StructuredLogger([MemoryLogSink()]))
            child = SerialWorkflow("child", [lambda context, value: value])
            parent = ChildWorkflow("parent", child)
            runtime.register_workflow(child)
            runtime.register_workflow(parent)
            runtime.apply_config(RuntimeConfig.from_dict({"workflows": [{"name": "parent"}]}))
            await runtime.start()
            with self.assertRaises(ConfigurationError):
                await runtime.run_workflow("parent", "value")
            await runtime.stop()

        self.run_async(scenario())

    def test_permission_is_checked_before_provider_execution(self):
        async def scenario():
            called = []
            runtime = Runtime(StructuredLogger([MemoryLogSink()]))
            runtime.register_component(
                FunctionComponent(
                    "protected",
                    {"read": lambda request, inv: called.append(True)},
                    capabilities={
                        "read": CapabilitySpec("read", permissions=frozenset({"filesystem.read"}))
                    },
                )
            )
            workflow = SerialWorkflow("protected-workflow", [lambda context, value: context.invoke("read", value)])
            runtime.register_workflow(workflow)
            runtime.apply_config(
                RuntimeConfig.from_dict(
                    {"workflows": [{"name": "protected-workflow"}], "permissions": {"allow": []}}
                )
            )
            await runtime.start()
            with self.assertRaises(PermissionDeniedError):
                await runtime.run_workflow("protected-workflow", None)
            self.assertEqual(called, [])
            await runtime.stop()

        self.run_async(scenario())

    def test_permissioned_capability_is_denied_without_an_allow_list(self):
        async def scenario():
            called = []
            runtime = Runtime(StructuredLogger([MemoryLogSink()]))
            runtime.register_component(
                FunctionComponent(
                    "protected",
                    {"read": lambda request, inv: called.append(True)},
                    capabilities={"read": CapabilitySpec("read", permissions={"filesystem.read"})},
                )
            )
            workflow = SerialWorkflow("protected-default-deny", [lambda context, value: context.invoke("read", value)])
            runtime.register_workflow(workflow)
            await runtime.start()
            with self.assertRaises(PermissionDeniedError):
                await runtime.run_workflow(workflow, None)
            self.assertEqual(called, [])
            await runtime.stop()

        self.run_async(scenario())

    def test_local_plugin_loads_from_manifest_and_can_be_selected_by_config(self):
        async def scenario():
            with TemporaryDirectory() as directory:
                root = Path(directory)
                plugin_dir = root / "demo"
                plugin_dir.mkdir()
                (plugin_dir / "astra.plugin.json").write_text(
                    json.dumps(
                        {
                            "id": "demo",
                            "version": "1",
                            "entrypoint": "plugin.py:create_components",
                            "components": ["demo.provider"],
                        }
                    ),
                    encoding="utf-8",
                )
                (plugin_dir / "plugin.py").write_text(
                    "from astra import FunctionComponent\n"
                    "def create_components():\n"
                    "    return [FunctionComponent('demo.provider', {'echo': lambda request, inv: 'plugin:' + request})]\n",
                    encoding="utf-8",
                )

                runtime = Runtime(StructuredLogger([MemoryLogSink()]))
                loaded = PluginLoader(root).load_selected(runtime, ["demo"])
                self.assertEqual(loaded[0].manifest.plugin_id, "demo")
                runtime.register_workflow(
                    SerialWorkflow("main", [lambda context, value: context.invoke("echo", value)])
                )
                runtime.apply_config(
                    RuntimeConfig.from_dict(
                        {
                            "components": ["demo.provider", "workflow:main"],
                            "workflows": [{"name": "main"}],
                            "bindings": {"echo": {"provider": "demo.provider"}},
                        }
                    )
                )
                await runtime.start()
                self.assertEqual(await runtime.run_workflow("main", "ok"), "plugin:ok")
                await runtime.stop()

        self.run_async(scenario())

    def test_plugin_registration_rolls_back_on_component_conflict(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            plugin_dir = root / "broken"
            plugin_dir.mkdir()
            (plugin_dir / "astra.plugin.json").write_text(
                json.dumps({"id": "broken", "version": "1", "entrypoint": "plugin.py:create_components"}),
                encoding="utf-8",
            )
            (plugin_dir / "plugin.py").write_text(
                "from astra import FunctionComponent\n"
                "def create_components():\n"
                "    return [FunctionComponent('new', {'new': lambda request, inv: request}), "
                "FunctionComponent('existing', {'other': lambda request, inv: request})]\n",
                encoding="utf-8",
            )
            runtime = Runtime(StructuredLogger([MemoryLogSink()]))
            runtime.register_component(FunctionComponent("existing", {"existing": lambda request, inv: request}))
            with self.assertRaises(ComponentLifecycleError):
                PluginLoader(root).load_selected(runtime, ["broken"])
            self.assertNotIn("new", runtime._components)

    def test_plugin_dependency_version_constraint_is_checked(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for plugin_id, manifest in (
                ("base", {"id": "base", "version": "2", "entrypoint": "plugin.py:create_components"}),
                (
                    "child",
                    {
                        "id": "child",
                        "version": "1",
                        "entrypoint": "plugin.py:create_components",
                        "dependencies": [{"id": "base", "version": "1"}],
                    },
                ),
            ):
                plugin_dir = root / plugin_id
                plugin_dir.mkdir()
                (plugin_dir / "astra.plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
            runtime = Runtime(StructuredLogger([MemoryLogSink()]))
            with self.assertRaises(PluginDependencyError):
                PluginLoader(root).load_selected(runtime, ["child"])


if __name__ == "__main__":
    unittest.main()
