"""SDK exception hierarchy."""


class OpsRiskSDKError(Exception):
    """Base class for all SDK errors."""


class APIError(OpsRiskSDKError):
    """HTTP error returned by the API (4xx / 5xx)."""

    def __init__(self, status_code: int, error_code: str, message: str, body: dict):
        super().__init__(f"[{status_code}] {error_code}: {message}")
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.body = body
        self.retryable: bool = body.get("retryable", False)
        self.retry_same_session: bool = body.get("retry_same_session", True)


class StepError(OpsRiskSDKError):
    """A pipeline step returned a FAILED state."""

    def __init__(self, step: str, detail: str = ""):
        super().__init__(f"Step '{step}' failed. {detail}".strip())
        self.step = step


class ValidationError(OpsRiskSDKError):
    """Client-side validation failed before any HTTP call was made."""

    def __init__(self, errors):
        # Accept either a list of error strings or a single string.
        if isinstance(errors, list):
            self.errors = errors
        else:
            self.errors = [errors]
        formatted = "\n".join(f"  • {e}" for e in self.errors)
        super().__init__(f"Validation failed ({len(self.errors)} issue(s)):\n{formatted}")


