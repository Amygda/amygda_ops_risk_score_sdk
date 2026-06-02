"""OpsRiskClient — top-level entry point for the amygda_ops_risk_score SDK."""

from __future__ import annotations

from typing import Any, Dict, Optional

from amygda_ops_risk_score._http import HTTPClient
from amygda_ops_risk_score.config import SessionConfig
from amygda_ops_risk_score.session import Session


class OpsRiskClient:
    """
    Synchronous client for the Ops Risk API.

    Usage::

        from amygda_ops_risk_score import OpsRiskClient, SessionConfig

        client = OpsRiskClient()               # uses the hosted API
        # client = OpsRiskClient("http://localhost:8000")  # local dev

        client.wait_until_ready()              # wait for API to be ready

        api_key = "yk-..."                     # from the Amygda portal

        config = SessionConfig(name="rail-may-2025")
        session = client.open_session(api_key=api_key, config=config)

        session.configure_labelling_pipeline("data/logs.csv", log_column="Description", ...)
        session.extract_keywords()
        session.generate_hierarchy()
        session.generate_weights()
        session.run_classification("outputs/")   # downloads zip, wipes session
    """

    _DEFAULT_BASE_URL = "https://amygda-ops-risk-score-api-433688334338.europe-west2.run.app"

    # Minimum API version this SDK requires.
    # Bump this only when the SDK starts calling an endpoint that didn't exist before.
    # If the live API is older than this, wait_until_ready() raises CompatibilityError.
    MIN_API_VERSION = "1.2.3"

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
    ):
        """
        Args:
            base_url:
                Override the API URL.  Leave as ``None`` to use the default hosted API.
                Pass ``'http://localhost:8000'`` when running the API locally for development.
            timeout:
                Default timeout in seconds for infrastructure calls only
                (health, open_session, status).
                Every pipeline step carries its own explicit timeout that overrides this.
        """
        url = (base_url or self._DEFAULT_BASE_URL).rstrip("/")
        self._http = HTTPClient(base_url=url, timeout=timeout)

    def close(self):
        """Close the underlying HTTP connection."""
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ------------------------------------------------------------------ #
    # User management
    # ------------------------------------------------------------------ #

    def get_user(self, api_key: str) -> Dict[str, Any]:
        """
        Look up a registered user by API key.

        Args:
            api_key:
                Your API key from the Amygda portal.

        Returns:
            Dict with ``api_key`` and ``created_at``.

        Raises:
            APIError: 404 if the key does not exist.
        """
        return self._http.get(f"/v1/api-keys/{api_key}")

    # ------------------------------------------------------------------ #
    # Session management
    # ------------------------------------------------------------------ #

    def open_session(
        self,
        api_key: str,
        config: SessionConfig,
        artifact_dir: Optional[str] = None,
    ) -> Session:
        """
        Open a new pipeline session and return a :class:`Session` object.

        Only one active session is allowed per user at a time.  If a previous
        session is still open, delete it first with :meth:`restart_session`.

        Args:
            api_key:
                Your permanent API key from the Amygda portal.
            config:
                A :class:`SessionConfig` with ``name``.
            artifact_dir:
                Optional local directory.  When set, every pipeline step automatically
                saves its result as ``{artifact_dir}/{step_name}.json``.
                ``generate_risk_scores`` also extracts ``risk_scores.parquet`` there.
                The directory is created on first write if it does not yet exist.

        Returns:
            A :class:`Session` ready for Step 1 (labelling) or ``import_model`` (risk score).
        """
        if not config.name or not config.name.strip():
            from amygda_ops_risk_score.exceptions import ValidationError
            raise ValidationError("SessionConfig.name is required and cannot be blank.")

        body: Dict[str, Any] = {
            "api_key": api_key,
            "name":    config.name,
        }
        resp = self._http.post("/v1/sessions/create", json=body)
        auth_id = resp["auth_id"]
        return Session(auth_id=auth_id, http=self._http, artifact_dir=artifact_dir)

    def get_session(self, auth_id: str, artifact_dir: Optional[str] = None) -> Session:
        """
        Re-attach to an existing session after a kernel restart.

        Makes one status check to confirm the session is still alive, then
        returns a fully functional :class:`Session` — no need to re-run any
        steps that are already ``DONE``.

        Args:
            auth_id:
                The session ID printed when you called :meth:`open_session`.
            artifact_dir:
                Same path used when opening the session so remaining steps continue
                writing artifacts to the correct directory.

        Returns:
            :class:`Session` reconnected to the existing server-side session.

        Raises:
            APIError: 404 if the session has expired or does not exist.  Call
                :meth:`open_session` to start fresh.
        """
        self._http.get(f"/v1/sessions/{auth_id}/status")
        return Session(auth_id=auth_id, http=self._http, artifact_dir=artifact_dir)

    def restart_session(
        self,
        session: Session,
        api_key: str,
        config: "SessionConfig",
    ) -> Session:
        """
        Delete the current session and open a fresh one in a single call.

        Use this when a step is locked (``StepAlreadyDoneError``) and you need
        to redo earlier steps.  Because only one active session is allowed per
        user, the existing session must be deleted before a new one can be created.

        .. warning::
            This deletes **all** session data — the database record and all stored
            files including any generated zips.  Download any artifacts you need
            (``session.run_classification()``, ``session.generate_risk_scores()``)
            **before** calling this.  The ``LabellingHistory`` and
            ``RiskScoreHistory`` records survive as permanent audit entries.

        Args:
            session:
                The active :class:`Session` to discard.
            api_key:
                Your API key (same one used to open the original session).
            config:
                A :class:`SessionConfig` for the new session.

        Returns:
            A new :class:`Session` starting from Step 1.
        """
        session.delete()
        return self.open_session(api_key=api_key, config=config)

    # ------------------------------------------------------------------ #
    # Infrastructure checks
    # ------------------------------------------------------------------ #

    def health(self) -> Dict[str, Any]:
        """
        Check whether the API process is running.

        Lightweight check with no model or database validation.
        Use :meth:`wait_until_ready` instead to confirm the API is fully
        initialised and all ML models are loaded.

        Returns
        -------
        Dict with ``status: 'ok'``.
        """
        return self._http.get("/v1/health")

    def ready(self) -> Dict[str, Any]:
        """
        Check whether all ML models are loaded and the API is ready to serve requests.

        Returns a 503 with ``status: 'loading'`` while models are still initialising
        (typically 60–120 s on a cold start).  Returns 200 with ``status: 'ready'``
        once all checks pass.

        Use :meth:`wait_until_ready` rather than calling this directly — it handles
        retries and progress output automatically.

        Returns
        -------
        Dict with ``status`` (``'ready'`` or ``'loading'``) and per-check details.
        """
        return self._http.get("/v1/ready")

    def wait_until_ready(
        self,
        timeout: float = 3600.0,
        interval: float = 5.0,
    ) -> Dict[str, Any]:
        """
        Poll the API until all ML models are loaded or ``timeout`` is reached.

        Call this at the start of every notebook session.  The API runs on
        Cloud Run with scale-to-zero — on a cold start it takes 60–120 s to
        load the ML models.  This method polls every ``interval`` seconds,
        prints progress dots, and returns as soon as the API is ready.
        On a warm instance it returns immediately.

        Args:
            timeout:
                Maximum seconds to wait (default 3600 s).  On a cold start the API
                can take 60–120 s to load ML models — the default covers this comfortably.
            interval:
                Seconds between polls (default 5 s).

        Returns:
            The ready-response dict (same as :meth:`ready`).

        Raises:
            TimeoutError: If the API is still not ready after ``timeout`` seconds.
            CompatibilityError: If the live API version is older than ``MIN_API_VERSION``.
        """
        import time
        import httpx
        from packaging.version import Version
        from amygda_ops_risk_score.exceptions import APIError, CompatibilityError

        deadline = time.monotonic() + timeout
        per_request_timeout = min(timeout, 300.0)  # avoid individual request timeouts longer than total timeout
        print("Waiting for API to be ready...", end="", flush=True)
        while True:
            try:
                resp = self._http.get("/v1/ready", timeout=per_request_timeout)
                if resp.get("status") == "ready":
                    print(" ready.", flush=True)
                    # Version compatibility check — runs once, after the API is ready
                    health = self._http.get("/v1/health")
                    api_version = health.get("api_version", "0.0.0")
                    if Version(api_version) < Version(self.MIN_API_VERSION):
                        raise CompatibilityError(
                            f"This SDK requires API >= {self.MIN_API_VERSION}. "
                            f"The server is running {api_version}. "
                            "Ask your admin to redeploy the latest API version."
                        )
                    return resp
            except APIError as exc:
                if exc.status_code != 503:
                    raise
            except httpx.ConnectError as exc:
                raise ConnectionError(
                    f"Cannot connect to the API at {self._http._client.base_url}. "
                    "Check your network connection or verify the API URL."
                ) from exc
            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.TimeoutException):
                pass
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                print(" timed out.", flush=True)
                raise TimeoutError(
                    f"API not ready after {timeout}s. "
                    "Check GET /v1/ready for details."
                )
            time.sleep(min(interval, remaining))
            print(".", end="", flush=True)
