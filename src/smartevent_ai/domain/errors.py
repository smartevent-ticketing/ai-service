"""Typed domain errors, independent of HTTP and infrastructure."""


class SmartEventError(Exception):
    """Base for expected application errors."""


class ContractViolation(SmartEventError):
    """Invalid tool arguments, response, or contract."""


class ToolUnavailable(SmartEventError):
    """Fail-closed: tool or required gate not approved."""


class BackendUnavailable(SmartEventError):
    """Backend response is untrusted, inaccessible or too large."""
