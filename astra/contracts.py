"""Stable contracts shared by components and workflows."""

from dataclasses import dataclass
from enum import Enum
from typing import FrozenSet, Optional


class InvocationMode(str, Enum):
    INVOKE = "invoke"
    STREAM = "stream"
    INVOKE_AND_STREAM = "invoke_and_stream"


class SideEffect(str, Enum):
    PURE = "pure"
    MANAGED_RESOURCE = "managed_resource"
    EXTERNAL_EFFECT = "external_effect"


@dataclass(frozen=True)
class CapabilitySpec:
    """The public contract exposed by a component."""

    name: str
    version: str = "1"
    mode: InvocationMode = InvocationMode.INVOKE
    side_effect: SideEffect = SideEffect.PURE
    permissions: FrozenSet[str] = frozenset()
    input_type: Optional[str] = None
    output_type: Optional[str] = None
    retry_safe: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("capability name must not be empty")
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("capability version must not be empty")
        if not isinstance(self.mode, InvocationMode):
            try:
                object.__setattr__(self, "mode", InvocationMode(self.mode))
            except (TypeError, ValueError) as exc:
                raise ValueError("capability mode is invalid") from exc
        if not isinstance(self.side_effect, SideEffect):
            try:
                object.__setattr__(self, "side_effect", SideEffect(self.side_effect))
            except (TypeError, ValueError) as exc:
                raise ValueError("capability side_effect is invalid") from exc
        if not isinstance(self.permissions, (frozenset, set, list, tuple)):
            raise ValueError("capability permissions must be a collection of strings")
        permissions = frozenset(self.permissions)
        if not all(isinstance(item, str) and item.strip() for item in permissions):
            raise ValueError("capability permissions must contain non-empty strings")
        object.__setattr__(self, "permissions", permissions)
        if not isinstance(self.retry_safe, bool):
            raise ValueError("capability retry_safe must be a boolean")


@dataclass(frozen=True)
class CapabilityRequirement:
    """A request for a capability in the current runtime scope."""

    name: str
    version: Optional[str] = None
    provider: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("capability requirement name must not be empty")
