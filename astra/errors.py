"""Errors with deterministic meanings at runtime boundaries."""


class AstraError(Exception):
    """Base class for errors raised by the Astra runtime."""


class ComponentLifecycleError(AstraError):
    """A component could not be started or stopped safely."""


class CapabilityNotFoundError(AstraError):
    """No started provider satisfies a capability requirement."""


class CapabilityVersionError(AstraError):
    """Providers exist, but none satisfies the requested version."""


class CapabilityModeError(AstraError):
    """A capability does not support the requested invoke or stream mode."""


class CapabilityAmbiguousError(AstraError):
    """More than one provider satisfies a requirement without a binding."""


class PermissionDeniedError(AstraError):
    """The current runtime scope is not authorized for a capability."""


class WorkflowError(AstraError):
    """A workflow could not select or execute its next step."""


class ConfigurationError(AstraError):
    """The external runtime configuration is invalid or unsafe."""


class SensitiveConfigurationError(ConfigurationError):
    """Sensitive data is not represented through the protected secret boundary."""


class PluginError(AstraError):
    """A local plugin could not be discovered, validated or loaded."""


class PluginManifestError(PluginError):
    """A plugin manifest is malformed or inconsistent with its package."""


class PluginDependencyError(PluginError):
    """A plugin dependency cannot be satisfied locally."""
