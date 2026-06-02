"""SDK exception hierarchy."""


class OpsRiskSDKError(Exception):
    """Base class for all SDK errors."""


class APIError(OpsRiskSDKError):
    """HTTP error returned by the API (4xx / 5xx).

    Attributes:
        status_code: HTTP status code (e.g. 404, 422, 500).
        error_code: Machine-readable error identifier from the API response.
        message: Human-readable error description.
        body: Full raw response body dict.
        retryable: True if the API indicates this error may succeed on retry.
        retry_same_session: False if the session is corrupted and a new one
            must be opened before retrying.
    """

    def __init__(self, status_code: int, error_code: str, message: str, body: dict):
        super().__init__(f"[{status_code}] {error_code}: {message}")
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.body = body
        self.retryable: bool = body.get("retryable", False)
        self.retry_same_session: bool = body.get("retry_same_session", True)


class StepError(OpsRiskSDKError):
    """A pipeline step returned a FAILED state.

    Attributes:
        step: Name of the step that failed (e.g. ``"generate_hierarchy"``).
    """

    def __init__(self, step: str, detail: str = ""):
        super().__init__(f"Step '{step}' failed. {detail}".strip())
        self.step = step


class ValidationError(OpsRiskSDKError):
    """Client-side validation failed before any HTTP call was made.

    Attributes:
        errors: List of human-readable validation error strings.
    """

    def __init__(self, errors):
        # Accept either a list of error strings or a single string.
        if isinstance(errors, list):
            self.errors = errors
        else:
            self.errors = [errors]
        formatted = "\n".join(f"  • {e}" for e in self.errors)
        super().__init__(f"Validation failed ({len(self.errors)} issue(s)):\n{formatted}")


class CompatibilityError(OpsRiskSDKError):
    """The live API version is older than this SDK requires.

    Raised by ``OpsRiskClient.wait_until_ready()`` when the API's ``api_version``
    is below ``OpsRiskClient.MIN_API_VERSION``.  Ask your admin to redeploy
    the latest API version.
    """


