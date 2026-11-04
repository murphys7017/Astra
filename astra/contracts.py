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

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("capability name must not be empty")
        if not self.version or not self.version.strip():
            raise ValueError("capability version must not be empty")


@dataclass(frozen=True)
class CapabilityRequirement:
    """A request for a capability in the current runtime scope."""

    name: str
    version: Optional[str] = None
    provider: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("capability requirement name must not be empty")
