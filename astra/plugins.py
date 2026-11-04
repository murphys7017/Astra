"""Trusted, local, in-process plugin discovery and transactional loading."""

from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Optional, Tuple
import uuid

from .errors import PluginDependencyError, PluginError, PluginManifestError
from .execution import Component, Runtime


MANIFEST_NAME = "astra.plugin.json"


@dataclass(frozen=True)
class PluginManifest:
    plugin_id: str
    version: str
    entrypoint: str
    declared_components: Tuple[str, ...] = ()
    dependencies: Tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "PluginManifest":
        required = {"id", "version", "entrypoint"}
        if not required.issubset(raw):
            raise PluginManifestError("plugin manifest requires id, version and entrypoint")
        unknown = set(raw) - required - {"components", "dependencies"}
        if unknown:
            raise PluginManifestError("unknown plugin manifest fields")
        plugin_id = raw["id"]
        version = raw["version"]
        entrypoint = raw["entrypoint"]
        if not all(isinstance(item, str) and item.strip() for item in (plugin_id, version, entrypoint)):
            raise PluginManifestError("plugin id, version and entrypoint must be non-empty strings")
        components = _string_tuple(raw.get("components", ()), "components")
        dependencies = _string_tuple(raw.get("dependencies", ()), "dependencies")
        return cls(plugin_id, version, entrypoint, components, dependencies)


@dataclass(frozen=True)
class LoadedPlugin:
    manifest: PluginManifest
    path: Path
    components: Tuple[Component, ...]


class PluginLoader:
    """Load only local plugin packages explicitly selected by the caller."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        if not self.root.exists() or not self.root.is_dir():
            raise PluginError("plugin root does not exist")

    def discover(self) -> Tuple[Tuple[Path, PluginManifest], ...]:
        discovered = []
        for path in sorted(self.root.iterdir(), key=lambda item: item.name):
            if not path.is_dir():
                continue
            manifest_path = path / MANIFEST_NAME
            if not manifest_path.is_file():
                continue
            try:
                raw = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest = PluginManifest.from_dict(raw)
            except (OSError, json.JSONDecodeError, TypeError) as exc:
                raise PluginManifestError("could not read plugin manifest") from exc
            discovered.append((path, manifest))
        return tuple(discovered)

    def load_selected(self, runtime: Runtime, selected: Optional[Iterable[str]] = None) -> Tuple[LoadedPlugin, ...]:
        if runtime.started:
            raise PluginError("plugins must be loaded before runtime start")
        entries = self.discover()
        by_id = {manifest.plugin_id: (path, manifest) for path, manifest in entries}
        if len(by_id) != len(entries):
            raise PluginManifestError("duplicate plugin id")
        if isinstance(selected, str):
            wanted = (selected,)
        else:
            wanted = tuple(selected) if selected is not None else tuple(by_id)
        for plugin_id in wanted:
            if plugin_id not in by_id:
                raise PluginDependencyError("selected plugin does not exist: {}".format(plugin_id))

        ordered_ids = _dependency_order(wanted, by_id)
        loaded: List[LoadedPlugin] = []
        registered_names: List[str] = []
        try:
            for plugin_id in ordered_ids:
                path, manifest = by_id[plugin_id]
                plugin = self._load_one(path, manifest)
                for component in plugin.components:
                    runtime.register_component(component)
                    registered_names.append(component.name)
                loaded.append(plugin)
        except Exception:
            for name in reversed(registered_names):
                runtime.unregister_component(name)
            raise
        return tuple(loaded)

    def _load_one(self, path: Path, manifest: PluginManifest) -> LoadedPlugin:
        module_name, separator, factory_name = manifest.entrypoint.partition(":")
        if not separator or not module_name or not factory_name:
            raise PluginManifestError("entrypoint must use module.py:factory format")
        module_path = (path / module_name).resolve()
        if path not in module_path.parents or not module_path.is_file():
            raise PluginManifestError("plugin entrypoint must be a file inside its package")
        imported_name = "astra_plugin_{}_{}".format(manifest.plugin_id, uuid.uuid4().hex)
        spec = importlib.util.spec_from_file_location(imported_name, module_path)
        if spec is None or spec.loader is None:
            raise PluginError("could not create plugin module spec")
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            raise PluginError("plugin module failed during import") from exc
        factory = getattr(module, factory_name, None)
        if not callable(factory):
            raise PluginManifestError("plugin factory is not callable")
        try:
            produced = factory()
        except Exception as exc:
            raise PluginError("plugin factory failed") from exc
        if isinstance(produced, Component):
            components = (produced,)
        else:
            try:
                components = tuple(produced)
            except TypeError as exc:
                raise PluginManifestError("plugin factory must return Component or iterable") from exc
        if not components or not all(isinstance(item, Component) for item in components):
            raise PluginManifestError("plugin factory returned a non-Component value")
        names = tuple(item.name for item in components)
        if len(set(names)) != len(names):
            raise PluginManifestError("plugin contains duplicate component names")
        if manifest.declared_components and set(manifest.declared_components) != set(names):
            raise PluginManifestError("manifest components do not match factory output")
        return LoadedPlugin(manifest, path, components)


def _dependency_order(
    wanted: Iterable[str],
    entries: Mapping[str, Tuple[Path, PluginManifest]],
) -> Tuple[str, ...]:
    order: List[str] = []
    visiting = set()
    visited = set()

    def visit(plugin_id: str) -> None:
        if plugin_id in visited:
            return
        if plugin_id in visiting:
            raise PluginDependencyError("plugin dependency cycle detected")
        try:
            manifest = entries[plugin_id][1]
        except KeyError as exc:
            raise PluginDependencyError("missing plugin dependency: {}".format(plugin_id)) from exc
        visiting.add(plugin_id)
        for dependency in manifest.dependencies:
            visit(dependency)
        visiting.remove(plugin_id)
        visited.add(plugin_id)
        order.append(plugin_id)

    for plugin_id in wanted:
        visit(plugin_id)
    return tuple(order)


def _string_tuple(value: Any, label: str) -> Tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise PluginManifestError("{} must be an array".format(label))
    result = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise PluginManifestError("{} must contain non-empty strings".format(label))
        result.append(item)
    return tuple(result)
