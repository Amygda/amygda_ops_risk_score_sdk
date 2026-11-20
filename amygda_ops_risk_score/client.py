"""OpsRiskClient — top-level entry point for the amygda_ops_risk_score SDK."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from amygda_ops_risk_score._http import HTTPClient
from amygda_ops_risk_score.config import SessionConfig
from amygda_ops_risk_score.exceptions import ValidationError
from amygda_ops_risk_score.session import Session


@dataclass
class DeploymentScores:
    """Result of :meth:`OpsRiskClient.score`."""

    scores: Any  # pandas.DataFrame, one row per asset and period
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        d = self.diagnostics
        return (
            f"DeploymentScores({len(self.scores)} rows, "
            f"{d.get('assets_scored')} assets, "
            f"{d.get('period_min')} to {d.get('period_max')}, "
            f"unmatched_share={d.get('unmatched_share')})"
        )


def _read_logs_file(path: str):
    import pandas as pd

    low = path.lower()
    if low.endswith(".parquet"):
        return pd.read_parquet(path)
    if low.endswith((".xlsx", ".xls")):
        return pd.read_excel(path)
    return pd.read_csv(path, low_memory=False)


def _to_parquet(df) -> bytes:
    """Parquet bytes for upload. Mixed-type text columns become text, keeping
    missing values missing (the server drops rows without an asset ID or time)."""
    import io

    import pandas as pd

    out = df.copy()
    for col in out.columns:
        if out[col].dtype == object:
            out[col] = out[col].map(lambda x: None if pd.isna(x) else str(x))
    buf = io.BytesIO()
    out.to_parquet(buf, index=False)
    return buf.getvalue()


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
    MIN_API_VERSION = "4.1.0"

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
    # Deployed models: deploy once, then score new data repeatedly
    # ------------------------------------------------------------------ #

    @staticmethod
    def _key_header(api_key: str) -> Dict[str, str]:
        return {"X-API-Key": api_key}

    def deployment_storage_policy(self) -> str:
        """What deploying a model stores, and for how long. Show this to the
        user before passing ``accept_storage=True`` to :meth:`deploy_model`."""
        return self._http.get("/v1/deployments/policy")["policy"]

    def deploy_model(
        self,
        api_key: str,
        model: str,
        name: str,
        *,
        accept_storage: bool,
        timeout: float = 300.0,
    ) -> Dict[str, Any]:
        """
        Deploy a trained model so new logs can be scored without a session.

        The scoring bundle is built **on your machine** from the model zip:
        settings, system/subsystem structure, weights, thresholds and log codes
        (fixed-log) or keywords (free-text). Raw logs, failures and scores in
        the zip are never uploaded. See :func:`helpers.build_scoring_bundle`.

        Args:
            api_key: Your API key from the Amygda portal.
            model: ``complete_model_<id>.zip`` from ``generate_risk_scores``,
                or a bundle already built with ``helpers.build_scoring_bundle``.
            name: A name for the deployment, unique for your organisation.
            accept_storage: Required, no default. ``True`` accepts that the
                bundle is stored on Amygda's servers until you delete it or it
                is unused for 90 days (:meth:`deployment_storage_policy`).
                If you can't accept that, keep scoring through sessions
                (a self-hosted scorer is coming soon).
            timeout: Seconds to wait for the upload and checks.

        Returns:
            Deployment details: ``deployment_id``, the column names new logs
            need, ``lookback`` (history to send before new logs), and more.
        """
        from amygda_ops_risk_score import _validators as v
        from amygda_ops_risk_score.deployment import (
            build_scoring_bundle,
            is_scoring_bundle,
        )

        v.validate_deploy_model(model, name, accept_storage)
        bundle_path, tmp_dir = model, None
        if not is_scoring_bundle(model):
            import tempfile

            tmp_dir = tempfile.mkdtemp(prefix="amygda-bundle-")
            bundle_path = os.path.join(tmp_dir, "bundle.zip")
            build_scoring_bundle(model, bundle_path)
        try:
            v.validate_bundle_size(bundle_path)
            with open(bundle_path, "rb") as fh:
                return self._http.post(
                    "/v1/deployments",
                    headers=self._key_header(api_key),
                    data={"name": name.strip(), "storage_accepted": "true"},
                    files={"bundle": ("bundle.zip", fh, "application/zip")},
                    timeout=timeout,
                )
        finally:
            if tmp_dir:
                import shutil

                shutil.rmtree(tmp_dir, ignore_errors=True)

    def list_deployments(self, api_key: str) -> List[Dict[str, Any]]:
        """List your organisation's deployments."""
        resp = self._http.get("/v1/deployments", headers=self._key_header(api_key))
        return resp["deployments"]

    def get_deployment(self, api_key: str, deployment_id: str) -> Dict[str, Any]:
        """One deployment's details, with ``last_scored_at`` and ``score_calls``."""
        from amygda_ops_risk_score import _validators as v

        v.validate_deployment_id(deployment_id)
        return self._http.get(
            f"/v1/deployments/{deployment_id}", headers=self._key_header(api_key)
        )

    def delete_deployment(self, api_key: str, deployment_id: str) -> Dict[str, Any]:
        """Delete a deployment and its stored bundle immediately."""
        from amygda_ops_risk_score import _validators as v

        v.validate_deployment_id(deployment_id)
        return self._http.delete(
            f"/v1/deployments/{deployment_id}", headers=self._key_header(api_key)
        )

    def score(
        self,
        api_key: str,
        deployment_id: str,
        logs,
        score_from=None,
        date_format: Optional[str] = None,
        timeout: float = 900.0,
    ) -> "DeploymentScores":
        """
        Score logs with a deployed model.

        Only the asset ID, timestamp and log columns the model was trained on
        are sent; other columns stay on your machine. Nothing sent is stored.

        To score new data correctly, include ``lookback`` worth of earlier logs
        (see :meth:`get_deployment`) and set ``score_from`` to the start of the
        new data. Periods before the one containing ``score_from`` are left
        out of the result. A period the previous upload cut short is returned
        again in full and should replace the earlier row.

        Args:
            api_key: Your API key.
            deployment_id: From :meth:`deploy_model` or :meth:`list_deployments`.
            logs: CSV, XLSX or parquet path, or a pandas DataFrame, in the
                same column layout as the training data.
            score_from: Optional start of the new data (e.g. ``'2026-11-18'``).
            date_format: Override the timestamp format saved with the model.
            timeout: Seconds to wait for scoring (server limit 15 minutes).

        Returns:
            :class:`DeploymentScores` with ``scores`` (one row per asset and
            period) and ``diagnostics`` (rows received, unmatched share, ...).
        """
        import io
        import json

        import pandas as pd

        from amygda_ops_risk_score import _validators as v

        v.validate_deployment_id(deployment_id)
        v.validate_score_input(logs, score_from)
        dep = self.get_deployment(api_key, deployment_id)
        required = {
            "asset ID": dep["asset_id_column"],
            "timestamp": dep["timestamp_column"],
            "log": dep["log_column"],
        }
        if isinstance(logs, pd.DataFrame):
            df = logs
        else:
            df = _read_logs_file(os.fspath(logs))
        v.validate_score_columns(df.columns, required)

        payload = _to_parquet(df[list(dict.fromkeys(required.values()))])
        if len(payload) > v.MAX_SCORE_UPLOAD_MB * 1024 * 1024:
            raise ValidationError(
                f"The logs are {len(payload) / 1048576:.1f} MB as parquet; the limit "
                f"is {v.MAX_SCORE_UPLOAD_MB} MB per call. Score shorter time ranges."
            )
        data: Dict[str, Any] = {"format": "parquet"}
        if score_from is not None:
            data["score_from"] = pd.Timestamp(score_from).isoformat()
        if date_format:
            data["date_format"] = date_format
        resp = self._http.post_raw(
            f"/v1/deployments/{deployment_id}/score",
            headers=self._key_header(api_key),
            data=data,
            files={"file": ("logs.parquet", payload, "application/vnd.apache.parquet")},
            timeout=timeout,
        )
        diagnostics = json.loads(resp.headers.get("X-Amygda-Diagnostics", "{}"))
        return DeploymentScores(
            scores=pd.read_parquet(io.BytesIO(resp.content)), diagnostics=diagnostics
        )

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
