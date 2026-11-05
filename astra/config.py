"""External JSON runtime configuration and immutable composition snapshots."""

from dataclasses import dataclass, field
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional, Tuple, Union

from .contracts import CapabilityRequirement
from .errors import ConfigurationError, SensitiveConfigurationError, WorkflowError


_TOP_LEVEL_KEYS = {
    "schema_version",
    "plugins",
    "components",
    "workflows",
    "bindings",
    "composition",
    "permissions",
    "resources",
    "secrets",
}
_SECRET_MARKERS = ("api_key", "apikey", "authorization", "credential", "password", "secret", "token")


def _secret_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(marker in normalized for marker in _SECRET_MARKERS)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigurationError("{} must be an object".format(label))
    return value


@dataclass(frozen=True)
class SecretValue:
    """A secret represented either by a reference or a protected inline value."""

    reference: Optional[str] = None
    value: Optional[str] = None
    protected: bool = False

    @property
    def is_inline(self) -> bool:
        return self.value is not None

    def __repr__(self) -> str:
        if self.reference is not None:
            return "SecretValue(reference={!r})".format(self.reference)
        return "SecretValue(value=<redacted>, protected={!r})".format(self.protected)


@dataclass(frozen=True)
class RuntimeConfig:
    schema_version: int
    plugin_refs: Tuple[str, ...] = ()
    component_names: Optional[Tuple[str, ...]] = None
    workflow_names: Optional[Tuple[str, ...]] = None
    workflow_order: Tuple[str, ...] = ()
    parallel_groups: Tuple[Tuple[str, ...], ...] = ()
    branches: Tuple[Mapping[str, Any], ...] = ()
    bindings: Mapping[str, CapabilityRequirement] = field(default_factory=lambda: MappingProxyType({}))
    workflow_params: Mapping[str, Mapping[str, Any]] = field(default_factory=lambda: MappingProxyType({}))
    permissions: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    resources: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    secrets: Mapping[str, SecretValue] = field(default_factory=lambda: MappingProxyType({}))

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "RuntimeConfig":
        data = _require_mapping(raw, "config")
        _validate_unscoped_secrets(data)
        unknown = set(data) - _TOP_LEVEL_KEYS
        if unknown:
            raise ConfigurationError("unknown config fields: {}".format(", ".join(sorted(map(str, unknown)))))
        version = data.get("schema_version", 1)
        if isinstance(version, bool) or not isinstance(version, int) or version != 1:
            raise ConfigurationError("schema_version must be 1")
        plugins = _string_tuple(data.get("plugins", ()), "plugins")
        components = _optional_string_tuple(data.get("components"), "components")
        _require_unique(plugins, "plugins")
        if components is not None:
            _require_unique(components, "components")

        workflow_entries = data.get("workflows")
        workflow_names: Optional[Tuple[str, ...]]
        params: Dict[str, Mapping[str, Any]] = {}
        if workflow_entries is None:
            workflow_names = None
        elif isinstance(workflow_entries, list):
            names = []
            declared_names = []
            for index, entry in enumerate(workflow_entries):
                item = _require_mapping(entry, "workflows[{}]".format(index))
                unknown_workflow_fields = set(item) - {"name", "enabled", "params"}
                if unknown_workflow_fields:
                    raise ConfigurationError("unknown workflow fields: {}".format(", ".join(sorted(map(str, unknown_workflow_fields)))))
                name = item.get("name")
                if not isinstance(name, str) or not name.strip():
                    raise ConfigurationError("workflows[{}].name must be a non-empty string".format(index))
                declared_names.append(name)
                enabled = item.get("enabled", True)
                if not isinstance(enabled, bool):
                    raise ConfigurationError("workflows[{}].enabled must be boolean".format(index))
                if enabled:
                    names.append(name)
                    params[name] = _freeze(_require_mapping(item.get("params", {}), "workflows[{}].params".format(index)))
            workflow_names = tuple(names)
            _require_unique(tuple(declared_names), "workflows")
            _require_unique(workflow_names, "workflows")
        else:
            raise ConfigurationError("workflows must be an array")

        composition = _require_mapping(data.get("composition", {}), "composition")
        unknown_composition_fields = set(composition) - {"order", "parallel", "branches"}
        if unknown_composition_fields:
            raise ConfigurationError("unknown composition fields: {}".format(", ".join(sorted(map(str, unknown_composition_fields)))))
        order = _string_tuple(composition.get("order", ()), "composition.order")
        _require_unique(order, "composition.order")
        parallel = _parallel_groups(composition.get("parallel", ()))
        if parallel and not order:
            raise ConfigurationError("composition.parallel requires composition.order")
        branches = _branch_tuple(composition.get("branches", ()))
        _validate_branch_graph(branches)

        binding_data = _require_mapping(data.get("bindings", {}), "bindings")
        bindings: Dict[str, CapabilityRequirement] = {}
        for capability, raw_binding in binding_data.items():
            if not isinstance(capability, str) or not capability.strip():
                raise ConfigurationError("binding capability name must be non-empty")
            item = _require_mapping(raw_binding, "bindings.{}".format(capability))
            unknown_binding_fields = set(item) - {"provider", "version"}
            if unknown_binding_fields:
                raise ConfigurationError("unknown binding fields for {}".format(capability))
            provider = item.get("provider")
            version_value = item.get("version")
            if provider is not None and (not isinstance(provider, str) or not provider.strip()):
                raise ConfigurationError("binding provider must be a non-empty string")
            if version_value is not None and (not isinstance(version_value, str) or not version_value.strip()):
                raise ConfigurationError("binding version must be a non-empty string")
            bindings[str(capability)] = CapabilityRequirement(str(capability), version_value, provider)

        permissions = _freeze(_require_mapping(data.get("permissions", {}), "permissions"))
        allow = permissions.get("allow")
        if allow is not None:
            if not isinstance(allow, tuple) or any(not isinstance(item, str) or not item.strip() for item in allow):
                raise ConfigurationError("permissions.allow must be an array of non-empty strings")
        resources = _freeze(_require_mapping(data.get("resources", {}), "resources"))
        unknown_resources = set(resources) - {"max_concurrent_children"}
        if unknown_resources:
            raise ConfigurationError("unknown resource fields: {}".format(", ".join(sorted(map(str, unknown_resources)))))
        max_concurrent_children = resources.get("max_concurrent_children")
        if max_concurrent_children is not None and (
            isinstance(max_concurrent_children, bool)
            or not isinstance(max_concurrent_children, int)
            or max_concurrent_children < 1
        ):
            raise ConfigurationError("resources.max_concurrent_children must be a positive integer")
        secrets = _parse_secrets(data.get("secrets", {}))
        return cls(
            schema_version=version,
            plugin_refs=plugins,
            component_names=components,
            workflow_names=workflow_names,
            workflow_order=order,
            parallel_groups=parallel,
            branches=branches,
            bindings=MappingProxyType(bindings),
            workflow_params=MappingProxyType(params),
            permissions=permissions,
            resources=resources,
            secrets=MappingProxyType(secrets),
        )

    @classmethod
    def from_json(cls, source: Union[str, Path]) -> "RuntimeConfig":
        path = Path(source)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigurationError("could not read JSON runtime config") from exc
        return cls.from_dict(raw)

    def redacted(self) -> Mapping[str, Any]:
        """Return diagnostics-safe configuration metadata without secret values."""
        return MappingProxyType(
            {
                "schema_version": self.schema_version,
                "plugins": self.plugin_refs,
                "components": self.component_names,
                "workflows": self.workflow_names,
                "workflow_order": self.workflow_order,
                "parallel_groups": self.parallel_groups,
                "branches": self.branches,
                "resources": dict(self.resources),
                "bindings": {
                    name: {"provider": req.provider, "version": req.version}
                    for name, req in self.bindings.items()
                },
                "secret_names": tuple(self.secrets),
            }
        )

    def validate_registered(self, components: Mapping[str, Any], workflows: Mapping[str, Any]) -> None:
        component_names = set(components)
        workflow_names = set(workflows)
        if self.component_names is not None:
            unknown = set(self.component_names) - component_names
            if unknown:
                raise ConfigurationError("unknown configured components: {}".format(", ".join(sorted(unknown))))
        if self.workflow_names is not None:
            unknown = set(self.workflow_names) - workflow_names
            if unknown:
                raise ConfigurationError("unknown configured workflows: {}".format(", ".join(sorted(unknown))))
        referenced_workflows = set(self.workflow_order)
        for group in self.parallel_groups:
            referenced_workflows.update(group)
        for branch in self.branches:
            referenced_workflows.add(str(branch["from"]))
            referenced_workflows.add(str(branch["to"]))
        unknown_references = referenced_workflows - workflow_names
        if unknown_references:
            raise ConfigurationError("composition references unknown workflows: {}".format(", ".join(sorted(unknown_references))))
        if self.workflow_names is not None:
            inactive_references = referenced_workflows - set(self.workflow_names)
            if inactive_references:
                raise ConfigurationError("composition references disabled workflows: {}".format(", ".join(sorted(inactive_references))))
        for capability, requirement in self.bindings.items():
            active_components = set(self.component_names) if self.component_names is not None else component_names
            if requirement.provider is not None and requirement.provider not in active_components:
                raise ConfigurationError(
                    "binding for {} references unknown component {}".format(capability, requirement.provider)
                )
        if self.workflow_order or self.parallel_groups or self.branches:
            from .workflow import ConfiguredWorkflow

            selected_workflows = (
                set(self.workflow_names) if self.workflow_names is not None else workflow_names
            )
            try:
                ConfiguredWorkflow(
                    "__config_validation__",
                    {name: workflows[name] for name in selected_workflows},
                    self.workflow_order,
                    self.parallel_groups,
                    self.branches,
                )
            except WorkflowError as exc:
                raise ConfigurationError("invalid composition: {}".format(exc)) from exc


@dataclass(frozen=True)
class CompositionSnapshot:
    generation: int
    config: RuntimeConfig

    @property
    def secret_names(self) -> Tuple[str, ...]:
        return tuple(self.config.secrets)

    def redacted(self) -> Mapping[str, Any]:
        data = dict(self.config.redacted())
        data["generation"] = self.generation
        return MappingProxyType(data)


def _string_tuple(value: Any, label: str) -> Tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ConfigurationError("{} must be an array".format(label))
    result = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ConfigurationError("{} must contain non-empty strings".format(label))
        result.append(item)
    return tuple(result)


def _optional_string_tuple(value: Any, label: str) -> Optional[Tuple[str, ...]]:
    if value is None:
        return None
    return _string_tuple(value, label)


def _parallel_groups(value: Any) -> Tuple[Tuple[str, ...], ...]:
    if not isinstance(value, (list, tuple)):
        raise ConfigurationError("composition.parallel must be an array")
    result = []
    seen = set()
    for group in value:
        names = _string_tuple(group, "composition.parallel group")
        _require_unique(names, "composition.parallel group")
        overlap = seen.intersection(names)
        if overlap:
            raise ConfigurationError("composition.parallel groups must not overlap")
        seen.update(names)
        result.append(names)
    return tuple(result)


def _branch_tuple(value: Any) -> Tuple[Mapping[str, Any], ...]:
    if not isinstance(value, (list, tuple)):
        raise ConfigurationError("composition.branches must be an array")
    result = []
    sources = set()
    for index, branch in enumerate(value):
        item = _require_mapping(branch, "composition.branches[{}]".format(index))
        required = {"from", "to"}
        unknown = set(item) - required
        if unknown:
            raise ConfigurationError("unknown composition branch fields")
        if not required.issubset(item):
            raise ConfigurationError("composition.branches[{}] requires from and to".format(index))
        if (
            not isinstance(item["from"], str)
            or not item["from"].strip()
            or not isinstance(item["to"], str)
            or not item["to"].strip()
        ):
            raise ConfigurationError("composition branch endpoints must be non-empty strings")
        if item["from"] in sources:
            raise ConfigurationError("composition.branches must have at most one outgoing edge per workflow")
        sources.add(item["from"])
        result.append(_freeze(item))
    return tuple(result)


def _validate_branch_graph(branches: Tuple[Mapping[str, Any], ...]) -> None:
    edges = {str(branch["from"]): str(branch["to"]) for branch in branches}
    for start in edges:
        seen = set()
        current = start
        while current in edges:
            if current in seen:
                raise ConfigurationError("composition.branches must not contain cycles")
            seen.add(current)
            current = edges[current]


def _require_unique(values: Tuple[str, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ConfigurationError("{} must not contain duplicates".format(label))


def _parse_secrets(value: Any) -> Dict[str, SecretValue]:
    data = _require_mapping(value, "secrets")
    result: Dict[str, SecretValue] = {}
    for name, raw in data.items():
        item = _require_mapping(raw, "secrets.{}".format(name))
        if set(item) not in ({"ref"}, {"value", "protected"}):
            raise SensitiveConfigurationError("secret {} must use a reference or a protected inline value".format(name))
        if "ref" in item:
            if not isinstance(item["ref"], str) or not item["ref"].strip():
                raise SensitiveConfigurationError("secret reference must be a non-empty string")
            result[str(name)] = SecretValue(reference=item["ref"])
        else:
            if not isinstance(item["value"], str) or item["protected"] is not True:
                raise SensitiveConfigurationError("inline secret must be marked protected")
            result[str(name)] = SecretValue(value=item["value"], protected=True)
    return result


def _validate_unscoped_secrets(value: Any, inside_secrets: bool = False, path: Tuple[str, ...] = ()) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            if key_text == "secrets" and path:
                raise SensitiveConfigurationError("secrets is only allowed at the top level")
            if not inside_secrets and key_text != "secrets" and _secret_key(key_text):
                raise SensitiveConfigurationError(
                    "sensitive field {} must be placed under protected secrets".format(key_text)
                )
            _validate_unscoped_secrets(item, inside_secrets or (key_text == "secrets" and not path), path + (key_text,))
    elif isinstance(value, (list, tuple)):
        for item in value:
            _validate_unscoped_secrets(item, inside_secrets, path)
