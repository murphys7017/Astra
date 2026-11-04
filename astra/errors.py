"""Errors with deterministic meanings at runtime boundaries."""


class AstraError(Exception):
    """Base class for errors raised by the Astra runtime."""


class ComponentLifecycleError(AstraError):
    """A component could not be started or stopped safely."""


class CapabilityNotFoundError(AstraError):
    """No started provider satisfies a capability requirement."""


class CapabilityVersionError(AstraError):
    """Providers exist, but none satisfies the requested version."""


class CapabilityAmbiguousError(AstraError):
    """More than one provider satisfies a requirement without a binding."""


class PermissionDeniedError(AstraError):
    """The current runtime scope is not authorized for a capability."""


class WorkflowError(AstraError):
    """A workflow could not select or execute its next step."""
