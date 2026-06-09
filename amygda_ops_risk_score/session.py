"""Session object — one instance per auth_id, wraps all pipeline steps."""

from __future__ import annotations

import json as _json
import os
import threading
import zipfile
from typing import Any, Callable, Dict, List, Optional

import amygda_ops_risk_score._validators as _v
from amygda_ops_risk_score._http import HTTPClient

# Step-specific messages shown while a blocking HTTP call is in-flight.
_BLOCKING_STEP_MESSAGES: dict = {
    "generate_hierarchy": [
        "Generating hierarchy — analysing keyword patterns...",
        "Still working — AI is mapping systems and subsystems...",
        "Building hierarchical structure from your keywords...",
        "Organising systems and subsystems, almost there...",
        "Finalising hierarchy, hang tight...",
    ],
    "run_classification": [
        "Running classification — building vector database...",
        "Classifying logs against the hierarchy...",
        "Probabilistic inference in progress...",
        "Processing classification results...",
        "Almost done — finalising predictions...",
    ],
    "run_training": [
        "Training in progress — classifying logs...",
        "Running feature engineering...",
        "Finding calibration thresholds...",
        "Building risk score model...",
        "Finalising training, this may take a few minutes...",
    ],
    "run_generation": [
        "Generating risk scores — classifying new logs...",
        "Feature engineering on new data...",
        "Calibrating features against trained thresholds...",
        "Calculating system-level risk scores...",
        "Computing operational risk, almost done...",
    ],
    "configure_labelling_pipeline": [
        "Uploading dataset and locking configuration...",
        "Still uploading — large files may take a moment...",
        "Validating dataset structure...",
        "Almost done — finalising configuration...",
    ],
    "downsample": [
        "Downsampling — applying stratified sampling...",
        "Still working — balancing class distribution...",
        "Almost done — finalising sample...",
    ],
    "extract_keywords": [
        "Extracting keywords from log text...",
        "Scanning text for domain terms...",
        "Filtering keyword pool and checking token budget...",
        "Applying frequency threshold scan...",
        "Almost done — finalising keyword list...",
    ],
    "update_hierarchy": [
        "Updating hierarchy with your edits...",
        "Validating hierarchy structure...",
        "Almost done — saving updated hierarchy...",
    ],
    "generate_weights": [
        "Locking hierarchy — generating criticality weights...",
        "Computing system and subsystem weights...",
        "Almost done — finalising weight assignments...",
    ],
    "update_weights": [
        "Updating criticality weights...",
        "Validating weight sums...",
        "Almost done — saving updated weights...",
    ],
    "import_model": [
        "Importing model zip — uploading artifact...",
        "Still uploading — large zips may take a moment...",
        "Validating model contents...",
        "Almost done — restoring session from zip...",
    ],
    "configure_training": [
        "Uploading training dataset and locking configuration...",
        "Still uploading — large files may take a moment...",
        "Validating column selections...",
        "Almost done — locking training configuration...",
    ],
    "configure_generation": [
        "Uploading generation dataset and locking configuration...",
        "Still uploading — large files may take a moment...",
        "Almost done — locking generation configuration...",
    ],
}
_DEFAULT_MESSAGES = ["Processing...", "Still working, please wait...", "Almost there..."]


def _elapsed_from(start: float) -> str:
    import time
    elapsed = time.monotonic() - start
    mins, secs = divmod(int(elapsed), 60)
    return f"{mins}m {secs}s" if mins else f"{secs}s"


def _spin_messages(step: str, stop_event: threading.Event, interval: float = 2.0) -> None:
    import time
    messages = _BLOCKING_STEP_MESSAGES.get(step, _DEFAULT_MESSAGES)
    msg_index = 0
    current_interval = interval
    start = time.monotonic()
    print(f"[{step}] {messages[0]}", flush=True)
    while not stop_event.wait(current_interval):
        msg_index = (msg_index + 1) % len(messages)
        print(f"[{step}] {messages[msg_index]} ({_elapsed_from(start)} elapsed)", flush=True)
        current_interval = min(current_interval * 2, 30.0)


class Session:
    """
    Represents a single ops-risk pipeline session.

    Obtain an instance via ``OpsRiskClient.open_session()``.
    """

    def __init__(
        self,
        auth_id: str,
        http: HTTPClient,
        artifact_dir: Optional[str] = None,
    ):
        self._auth_id = auth_id
        self._http = http
        self._artifact_dir = artifact_dir

    @property
    def auth_id(self) -> str:
        return self._auth_id

    # ------------------------------------------------------------------ #
    # Session management
    # ------------------------------------------------------------------ #

    def status(self) -> Dict[str, Any]:
        """
        Return the current session status and the state of every pipeline step.

        Each step has a ``state`` field:

        - ``NONE``    — not started yet, safe to proceed
        - ``RUNNING`` — currently executing on the server
        - ``DONE``    — completed successfully, skip it
        - ``FAILED``  — failed, safe to re-run

        Use this after a kernel restart to check where you left off before
        re-submitting any steps.

        Returns:
            Dict with ``auth_id``, ``api_key``, ``name``, ``created_at``,
            ``expires_at``, ``steps`` (mapping of step name → step state dict),
            ``config``, ``artifacts``, and ``current_error``.
        """
        return self._http.get(f"/v1/sessions/{self._auth_id}/status")

    def delete(self) -> Dict[str, Any]:
        """
        Delete this session and all associated stored files.

        Prefer :meth:`OpsRiskClient.restart_session` when you want to start over,
        as it handles deletion and re-creation in one call.  Call this directly
        only if you need to free up the session slot without immediately opening
        a new one.

        Returns:
            Dict with ``message`` and ``auth_id``.
        """
        return self._http.delete(f"/v1/sessions/{self._auth_id}")

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _save_artifact(self, step_name: str, data: dict) -> None:
        """Write ``data`` as ``{artifact_dir}/{step_name}.json`` if artifact_dir is set."""
        if not self._artifact_dir:
            return
        os.makedirs(self._artifact_dir, exist_ok=True)
        path = os.path.join(self._artifact_dir, f"{step_name}.json")
        with open(path, "w") as fh:
            _json.dump(data, fh, indent=2, default=str)

    def _run_blocking(self, step: str, http_call: Callable, interval: float = 2.0) -> Any:
        """Run a blocking HTTP call while printing rotating step messages in a thread."""
        stop = threading.Event()
        t = threading.Thread(target=_spin_messages, args=(step, stop, interval), daemon=True)
        t.start()
        try:
            result = http_call()
        finally:
            stop.set()
            t.join()
        print(f"[{step}] Complete.", flush=True)
        return result

    def _step_done_data(self, step_name: str) -> Dict[str, Any]:
        """Fetch the DONE extra fields for *step_name* from the live session status."""
        try:
            info = self._http.get(f"/v1/sessions/{self._auth_id}/status")
            step = info.get("steps", {}).get(step_name, {})
            return {k: v for k, v in step.items() if k != "state"}
        except Exception:
            return {}

    def _download_and_wipe(self, url_path: str, dest_path: str) -> str:
        """
        Stream a file from ``url_path`` to ``dest_path``, then wipe the session.

        If the download fails the session is left intact so the caller can retry.
        Returns the absolute path written.
        """
        from amygda_ops_risk_score.exceptions import APIError

        full_url = f"{self._http._client.base_url}{url_path}"
        with self._http._client.stream(
            "GET", full_url, params={"auth_id": self._auth_id}
        ) as r:
            if not r.is_success:
                body = r.read()
                try:
                    parsed = _json.loads(body)
                except Exception:
                    parsed = {"message": body.decode(errors="replace")}
                raise APIError(
                    status_code=r.status_code,
                    error_code=parsed.get("error", "unknown_error"),
                    message=parsed.get("message", ""),
                    body=parsed,
                )
            with open(dest_path, "wb") as fh:
                for chunk in r.iter_bytes(chunk_size=65536):
                    fh.write(chunk)

        # Download succeeded — wipe session from all stores
        self.delete()
        return os.path.abspath(dest_path)

    # ------------------------------------------------------------------ #
    # Labelling — Step 1: configure_labelling_pipeline
    # Re-runnable until Step 2 (downsample) or Step 3 (extract_keywords) starts.
    # ------------------------------------------------------------------ #

    def configure_labelling_pipeline(
        self,
        file_path: str,
        log_column: str,
        max_systems: int,
        max_subsystems: int,
        asset_context: str,
        is_free_text: bool,
        sheet_name: Optional[str] = None,
        *,
        timeout: float = 600.0,
    ) -> Dict[str, Any]:
        """
        Upload the log dataset and lock the labelling pipeline configuration.

        This is Step 1 of the labelling pipeline and must be run before any other
        labelling step.  Can be re-run until Step 2 (downsample) or
        Step 3 (extract_keywords) starts.

        Args:
            file_path:
                Path to the log file (.csv or .xlsx).
            log_column:
                Name of the column containing the log text or event code.
            max_systems:
                Maximum number of top-level systems for the LLM to generate (1–10).
            max_subsystems:
                Maximum number of subsystems per system (1–5).
            asset_context:
                Plain-English description of the asset being analysed
                (e.g. ``'rail rolling stock'``).  Helps the LLM generate
                relevant system and subsystem names.
            is_free_text:
                ``True`` if logs are free-form text descriptions.
                ``False`` if they are structured codes or short category labels.
            sheet_name:
                XLSX only — sheet to read.  ``None`` auto-detects the first sheet.
            timeout:
                Maximum seconds to wait for upload and validation (default 600 s).

        Returns:
            Dict with ``message``, ``auth_id``, ``row_count``, ``downsample_required``
            (bool), ``available_columns``, ``next_step``, and your full configuration
            echoed back (``file_path``, ``log_column``, ``max_systems``,
            ``max_subsystems``, ``asset_context``, ``is_free_text``, ``sheet_name``).
        """
        _v.validate_configure(
            file_path=file_path,
            log_column=log_column,
            max_systems=max_systems,
            max_subsystems=max_subsystems,
            asset_context=asset_context,
            is_free_text=is_free_text,
            sheet_name=sheet_name,
        )
        data = {
            "auth_id":        self._auth_id,
            "log_column":     log_column,
            "max_systems":    str(max_systems),
            "max_subsystems": str(max_subsystems),
            "asset_context":  asset_context,
            "is_free_text":   str(is_free_text).lower(),
        }
        if sheet_name:
            data["sheet_name"] = sheet_name

        def _call():
            with open(file_path, "rb") as fh:
                filename = os.path.basename(file_path)
                return self._http.post(
                    "/v1/labelling/configure",
                    data=data,
                    files={"file": (filename, fh)},
                    timeout=timeout,
                )

        raw = self._run_blocking("configure_labelling_pipeline", _call)
        result = {
            **raw,
            "auth_id":        self._auth_id,
            "file_path":      os.path.abspath(file_path),
            "log_column":     log_column,
            "max_systems":    max_systems,
            "max_subsystems": max_subsystems,
            "asset_context":  asset_context,
            "is_free_text":   is_free_text,
            "sheet_name":     sheet_name,
        }
        self._save_artifact("configure_labelling_pipeline", result)
        return result

    # ------------------------------------------------------------------ #
    # Labelling — Step 2: downsample
    # Re-runnable until Step 3 (extract_keywords) starts.
    # ------------------------------------------------------------------ #

    def downsample(
        self,
        sample_size: int,
        asset_column: Optional[str] = None,
        vehicle_column: Optional[str] = None,
        timestamp_column: Optional[str] = None,
        *,
        file_path: Optional[str] = None,
        sheet_name: Optional[str] = None,
        timeout: float = 600.0,
    ) -> Dict[str, Any]:
        """
        Stratified downsample — only callable if downsample_required == true.

        At least one of asset_column, vehicle_column, timestamp_column must be provided.

        Pass ``file_path`` (same file used in ``configure``) to validate column names
        client-side before sending the request.

        Args:
            sample_size:
                Target number of rows after downsampling.
            asset_column:
                Column identifying the physical asset (e.g. train number).
            vehicle_column:
                Column identifying the vehicle within an asset.
            timestamp_column:
                Column containing the event timestamp — used for stratification.
            file_path:
                Optional path to the original log file for client-side column validation.
            sheet_name:
                XLSX only.  ``None`` auto-detects the first sheet.
            timeout:
                Maximum seconds to wait (default 600 s).

        Returns:
            Dict with ``message``, ``auth_id``, ``original_rows``, ``sampled_rows``,
            ``next_step``, and your column selections echoed back.  Also includes
            ``downsampled_path`` (absolute path to ``downsampled.parquet``) when
            ``artifact_dir`` is set.
        """
        _v.validate_downsample(
            sample_size=sample_size,
            asset_column=asset_column,
            vehicle_column=vehicle_column,
            timestamp_column=timestamp_column,
            file_path=file_path,
            sheet_name=sheet_name,
        )
        body: Dict[str, Any] = {
            "auth_id":     self._auth_id,
            "sample_size": sample_size,
        }
        if asset_column:
            body["asset_column"] = asset_column
        if vehicle_column:
            body["vehicle_column"] = vehicle_column
        if timestamp_column:
            body["timestamp_column"] = timestamp_column

        raw = self._run_blocking(
            "downsample",
            lambda: self._http.post("/v1/labelling/downsample", json=body, timeout=timeout),
        )
        result: Dict[str, Any] = {
            **raw,
            "auth_id":           self._auth_id,
            "sample_size":       sample_size,
            "asset_column":      asset_column,
            "vehicle_column":    vehicle_column,
            "timestamp_column":  timestamp_column,
        }

        # Download the actual downsampled rows into artifact_dir when set
        if self._artifact_dir:
            os.makedirs(self._artifact_dir, exist_ok=True)
            dest = os.path.join(self._artifact_dir, "downsampled.parquet")
            try:
                full_url = (
                    f"{self._http._client.base_url}"
                    f"/v1/labelling/download-downsampled"
                )
                with self._http._client.stream(
                    "GET", full_url, params={"auth_id": self._auth_id}
                ) as r:
                    if r.is_success:
                        with open(dest, "wb") as fh:
                            for chunk in r.iter_bytes(chunk_size=65536):
                                fh.write(chunk)
                        result["downsampled_path"] = os.path.abspath(dest)
            except Exception:
                pass  # metadata result is intact — download is best-effort

        self._save_artifact("downsample", result)
        return result

    # ------------------------------------------------------------------ #
    # Labelling — Step 3: extract_keywords
    # Re-runnable until Step 4 (generate_hierarchy) starts.
    # ------------------------------------------------------------------ #

    def extract_keywords(
        self,
        extraction_method: str = "fast",
        *,
        timeout: float = 1200.0,
    ) -> Dict[str, Any]:
        """
        Scan the uploaded log dataset and extract a domain vocabulary.

        This is Step 3.  The keywords feed directly into :meth:`generate_hierarchy`
        — the more accurate the keyword list, the better the LLM-generated hierarchy.
        Can be re-run until Step 4 (generate_hierarchy) starts.

        Args:
            extraction_method:
                ``'fast'`` (default) uses TF-IDF and works well for most datasets.
                ``'deep'`` uses spaCy and produces better results for noisy or heavily
                abbreviated log text, but runs slower.
            timeout:
                Maximum seconds to wait (default 1200 s).  Increase for very large
                datasets (100 k+ rows).

        Returns:
            Dict with ``message``, ``auth_id``, ``extraction_method``,
            ``raw_keyword_count``, ``filtered_keyword_count``,
            ``linguistic_keywords_removed``, ``keywords`` (list), ``keyword_pool``
            (frequency map), and ``next_step``.
        """
        _v.validate_extract_keywords(extraction_method)
        raw = self._run_blocking(
            "extract_keywords",
            lambda: self._http.post(
                "/v1/labelling/extract-keywords",
                json={"auth_id": self._auth_id, "extraction_method": extraction_method},
                timeout=timeout,
            ),
        )
        result = {**raw, "auth_id": self._auth_id, "extraction_method": extraction_method}
        self._save_artifact("extract_keywords", result)
        return result

    # ------------------------------------------------------------------ #
    # Labelling — Step 4: generate_hierarchy
    # Re-runnable until Step 5 (update_hierarchy) or Step 6 (generate_weights) starts.
    # ------------------------------------------------------------------ #

    def generate_hierarchy(
        self,
        *,
        keywords: Optional[List[str]] = None,
        timeout: float = 1200.0,
    ) -> Dict[str, Any]:
        """
        Send extracted keywords to the LLM to build a system/subsystem hierarchy.

        This is Step 4.  The LLM groups the keywords into systems and subsystems
        based on the ``asset_context`` and limits set in :meth:`configure`.
        Blocks until complete — typical runtime is 30 s to 3 min.
        Can be re-run until Step 5 (update_hierarchy) or Step 6 (generate_weights) starts.

        Args:
            keywords:
                Optional list of keywords to use instead of the ones extracted by
                :meth:`extract_keywords`.  If provided, the server applies linguistic
                validation (same as ``extract_keywords``) before building the hierarchy.
                ``extract_keywords`` must still be completed first.
                If ``None`` (default), the server uses the pool from ``extract_keywords``.
            timeout:
                Maximum seconds to wait (default 1200 s).  Increase for large keyword
                pools (5 k+ keywords) where LLM processing takes longer.

        Returns:
            Dict with ``message``, ``auth_id``, ``hierarchy`` (list of
            system/subsystem rows with confidence scores), ``systems_count``,
            ``subsystems_count``, ``keywords_source`` (``"extract_keywords"`` or
            ``"user_override"``), ``keywords_finalised`` (the keyword pool
            actually used — after linguistic filtering), and ``keywords_dropped``
            (keywords removed during filtering, ``None`` when using extracted pool).
            Shape is the same whether or not ``keywords`` is provided.
        """
        if keywords is not None:
            _v.validate_generate_hierarchy(keywords)
        raw = self._run_blocking(
            "generate_hierarchy",
            lambda: self._http.post(
                "/v1/labelling/generate-hierarchy",
                params={"auth_id": self._auth_id},
                json={"keywords": keywords} if keywords is not None else None,
                timeout=timeout,
            ),
        )
        # API is synchronous — response body already contains all step data.
        # No second DB read needed (same pattern as update_hierarchy / accept_hierarchy).
        result = {**raw, "auth_id": self._auth_id}
        self._save_artifact("generate_hierarchy", result)
        return result

    # ------------------------------------------------------------------ #
    # Labelling — Step 5: update_hierarchy  (repeatable)
    # Re-runnable until Step 6 (generate_weights) starts.
    # ------------------------------------------------------------------ #

    def update_hierarchy(
        self,
        rows: List[Dict[str, Any]],
        *,
        timeout: float = 1200.0,
    ) -> Dict[str, Any]:
        """
        Submit a refined hierarchy.

        ``rows`` is a list of dicts with keys:
          system, system_confidence, subsystem, subsystem_confidence

        ``system_confidence`` and ``subsystem_confidence`` must be
        ``"high"``, ``"medium"``, or ``"low"``.

        Can be called multiple times — each call overwrites the previous result.
        Locked once ``generate_weights`` is called.

        Args:
            rows:
                List of dicts with keys ``system``, ``system_confidence``,
                ``subsystem``, and ``subsystem_confidence``.
            timeout:
                Maximum seconds to wait (default 1200 s).

        Returns:
            Dict with ``message``, ``auth_id``, ``status``, ``systems_count``,
            ``subsystems_count``, ``hierarchy`` (the saved rows), ``next_step``,
            and ``rows`` (the input echoed back).
        """
        _v.validate_update_hierarchy(rows)
        raw = self._run_blocking(
            "update_hierarchy",
            lambda: self._http.post(
                "/v1/labelling/update-hierarchy",
                json={"auth_id": self._auth_id, "rows": rows},
                timeout=timeout,
            ),
        )
        result = {**raw, "auth_id": self._auth_id, "rows": rows}
        self._save_artifact("update_hierarchy", result)
        return result

    # ------------------------------------------------------------------ #
    # Labelling — Step 6: generate_weights
    # Re-runnable until Step 8 (run_classification) starts.
    # ------------------------------------------------------------------ #

    def generate_weights(
        self,
        *,
        timeout: float = 300.0,
    ) -> Dict[str, Any]:
        """
        Lock the current hierarchy and generate criticality weights.

        Locks whichever hierarchy is current — the output of
        :meth:`generate_hierarchy` if :meth:`update_hierarchy` was never called,
        or the latest :meth:`update_hierarchy` result if it was.

        If you ran :meth:`update_hierarchy` and want to discard those changes,
        re-run :meth:`update_hierarchy` with the original rows from your
        ``generate_hierarchy.json`` artifact, then call this method.

        Can be re-run until Step 8 (run_classification) starts.

        Args:
            timeout:
                Maximum seconds to wait (default 300 s).

        Returns:
            Dict with ``message``, ``auth_id``, ``systems_count``, ``next_step``,
            and ``weights`` — a list of dicts, each with ``system_name``, ``weight``,
            and ``subsystems`` (list of ``{subsystem_name, weight}``).
            Pass ``result["weights"]`` to :meth:`update_weights` to adjust before classifying.
        """
        raw = self._run_blocking(
            "generate_weights",
            lambda: self._http.post(
                "/v1/labelling/accept-hierarchy",
                json={"auth_id": self._auth_id, "decision": "accept"},
                timeout=timeout,
            ),
        )
        result = {**raw, "auth_id": self._auth_id}
        self._save_artifact("generate_weights", result)
        return result

    # ------------------------------------------------------------------ #
    # Labelling — Step 7: update_weights  (repeatable)
    # Re-runnable until Step 8 (run_classification) starts.
    # ------------------------------------------------------------------ #

    def update_weights(
        self,
        systems: List[Dict[str, Any]],
        *,
        original_systems: Optional[List[Dict[str, Any]]] = None,
        timeout: float = 1200.0,
    ) -> Dict[str, Any]:
        """
        Override system/subsystem criticality weights.

        ``systems`` is a list of dicts with keys:
          system_name, weight, subsystems (list of {subsystem_name, weight})

        All system weights must sum to 1.0.
        Each system's subsystem weights must sum to 1.0.

        Pass ``original_systems=result["weights"]`` (from :meth:`generate_weights` or a
        previous :meth:`update_weights` call) to enable name-change protection — any
        attempt to rename a system or subsystem will raise ``ValidationError`` before
        the HTTP call is made.  Use ``helpers.make_weight_update()`` to get a safely
        editable copy.

        Can be called multiple times — each call overwrites the previous weights.
        Locked once ``run_classification`` is called.

        Weights do not need to sum to 1.0 before passing — ``update_weights``
        automatically normalises them using the same pin-and-redistribute logic
        as the UI: values you changed relative to ``original_systems`` are locked,
        and only the unchanged values are scaled to fill the remaining budget.

        Args:
            systems:
                List of dicts with keys ``system_name``, ``weight``, and ``subsystems``
                (list of ``{subsystem_name, weight}``).
            original_systems:
                The unmodified weights list from :meth:`generate_weights` or a previous
                :meth:`update_weights` call.  Enables name-change protection when provided.
            timeout:
                Maximum seconds to wait (default 1200 s).

        Returns:
            Dict with ``message``, ``auth_id``, ``systems_count``, ``next_step``,
            and ``weights`` (the normalised systems list after saving).
        """
        from amygda_ops_risk_score.helpers import normalize_weights as _norm
        systems = _norm(systems, original_systems=original_systems)
        _v.validate_update_weights(systems, original_systems=original_systems)
        raw = self._run_blocking(
            "update_weights",
            lambda: self._http.post(
                "/v1/labelling/update-weights",
                json={"auth_id": self._auth_id, "systems": systems},
                timeout=timeout,
            ),
        )
        result = {**raw, "auth_id": self._auth_id, "systems": systems}
        self._save_artifact("update_weights", result)
        return result

    # ------------------------------------------------------------------ #
    # Labelling — Step 8: run_classification  (one-way door)
    # ------------------------------------------------------------------ #

    def run_classification(
        self,
        dest_dir: str,
        *,
        timeout: float = 3600.0,
    ) -> Dict[str, Any]:
        """
        Run classification.  ONE-WAY DOOR — cannot be repeated.

        Blocks until complete, then automatically downloads
        ``trained_labelling_model_{auth_id}.zip`` to ``dest_dir`` and wipes the session.

        Args:
            dest_dir:
                Directory to save the zip into.  Created if it does not exist.
            timeout:
                Maximum seconds to wait for the server to finish (default 1 h).

        Returns:
            Dict with ``auth_id``, ``zip_path`` (absolute local path of the downloaded
            zip), ``dest_dir``, and ``total_rows``.

        Example
        -------
        ::

            result = session.run_classification("outputs/")
            zip_path = result["zip_path"]
            # → "/abs/path/outputs/trained_labelling_model_ses-xxxx.zip"
            # Session is wiped automatically.
            # Use this zip with import_model() on a new risk score session.
        """
        os.makedirs(dest_dir, exist_ok=True)
        raw = self._run_blocking(
            "run_classification",
            lambda: self._http.post(
                "/v1/labelling/run-classification",
                params={"auth_id": self._auth_id},
                timeout=timeout,
            ),
        )
        dest_path = os.path.join(dest_dir, f"trained_labelling_model_{self._auth_id}.zip")
        abs_path = self._download_and_wipe("/v1/labelling/download-zip", dest_path)
        result = {
            "auth_id":   self._auth_id,
            "zip_path":  abs_path,
            "dest_dir":  os.path.abspath(dest_dir),
            "total_rows": raw.get("total_rows", 0),
        }
        self._save_artifact("run_classification", result)
        return result

    # ------------------------------------------------------------------ #
    # Risk Score — import model (Path B — skip labelling)
    # ------------------------------------------------------------------ #

    def import_model(self, zip_path: str, *, timeout: float = 600.0) -> Dict[str, Any]:
        """
        Upload a model zip to this session, skipping the labelling pipeline.

        Two zip types are accepted:

        **Labelling zip** (``trained_labelling_model_{auth_id}.zip`` from ``run_classification``):
            Contains labelling artifacts only — hierarchy, weights, Qdrant model,
            model_config.json.  Unlocks ``configure_training`` → ``run_training``
            → ``configure_generation`` → ``run_generation``.

        **Complete model zip** (``complete_model_{auth_id}.zip`` from ``run_generation``):
            Contains labelling artifacts **plus** training thresholds and risk score
            config.  Automatically skips ``configure_training`` + ``run_training``
            — unlocks ``configure_generation`` directly.  Use this to re-run
            generation on new logs without re-training.

        .. note::
            To **retrain from scratch** on a previously-trained session, import the
            labelling zip (not the complete model zip) so training is not skipped.

        Args:
            zip_path:
                Path to the zip file produced by :meth:`run_classification` or
                :meth:`generate_risk_scores`.
            timeout:
                Maximum seconds to wait for upload and extraction (default 600 s).

        Returns:
            Dict with ``message``, ``auth_id``, ``is_free_text``, ``log_column``,
            ``risk_training_restored`` (bool — True if the zip included calibration
            thresholds, allowing you to skip straight to ``configure_generation``),
            ``next_step``, and ``zip_path``.
        """
        _v.validate_import_model(zip_path)

        def _call():
            with open(zip_path, "rb") as fh:
                filename = os.path.basename(zip_path)
                return self._http.post(
                    "/v1/risk-score/import-model",
                    data={"auth_id": self._auth_id},
                    files={"file": (filename, fh, "application/zip")},
                    timeout=timeout,
                )

        raw = self._run_blocking("import_model", _call)
        result = {**raw, "auth_id": self._auth_id, "zip_path": os.path.abspath(zip_path)}
        self._save_artifact("import_model", result)
        return result

    # ------------------------------------------------------------------ #
    # Risk Score — Step 9: configure_training
    # Re-runnable until Step 10 (run_training) starts.
    # ------------------------------------------------------------------ #

    def configure_training(
        self,
        file_path: str,
        asset_id_column: str,
        timestamp_column: str,
        date_format: str = "infer",
        rolling_window: int = 7,
        rolling_feature_type: str = "sum",
        quantile_for_thresholds: float = 0.99,
        sheet_name: Optional[str] = None,
        supervised: bool = False,
        failures_path: Optional[str] = None,
        failure_date_column: str = "machine_initialisation_date",
        failure_date_format: str = "infer",
        prediction_horizon_days: int = 14,
        exclusion_days_after: int = 7,
        target_imbalance_ratio: Optional[float] = 10.0,
        sampling_strategy: str = "block",
        block_size_days: int = 14,
        n_candidates: int = 200,
        fallback_quantile: float = 0.95,
        min_positives: int = 5,
        lr_c: float = 0.5,
        *,
        timeout: float = 600.0,
    ) -> Dict[str, Any]:
        """
        Upload historical log data and set the risk score training parameters.

        This is Step 9.  The training step uses this data to learn per-subsystem
        calibration thresholds — the activity levels that separate normal from
        elevated risk for each system component.

        Can be re-run until Step 10 (train_risk_model) starts.

        Args:
            file_path:
                Path to the historical log file (.csv or .xlsx).  Must contain the
                same log column as the dataset used in the labelling notebook.
        asset_id_column:
            Column that uniquely identifies each asset (e.g. train number, vehicle ID).
        timestamp_column:
            Column containing the event timestamp.  Used to build rolling time windows.
        date_format:
            ``'infer'`` lets pandas auto-detect the format.  Pass a strftime string
            (e.g. ``'%d/%m/%Y'``) if auto-detection fails.
        rolling_window:
            Number of days to aggregate events over (1–30, default 7).
        rolling_feature_type:
            How events are aggregated in the rolling window.
            ``'sum'`` counts total events; ``'flag'`` marks any-or-none;
            ``'ewm'`` applies exponential weighting (more weight on recent days);
            ``'all'`` runs sum + flag + ewm together.
            **``'ewm'`` and ``'all'`` are only valid for fixed-log sessions.**
            Free-text sessions use Qdrant classification and only support ``'sum'`` or ``'flag'``.
        quantile_for_thresholds:
            Calibration percentile (0–1, default 0.99).  0.99 means the top 1 %
            of activity triggers an elevated risk signal.
        sheet_name:
            XLSX only.  ``None`` auto-detects the first sheet.
        supervised:
            When ``True``, uses AUC-ROC optimisation to learn per-subsystem thresholds
            and logistic regression to learn system/subsystem weights from failure events.
            Requires ``failures_path``.
        failures_path:
            Path to a CSV containing failure event dates.  Required when ``supervised=True``.
            Must contain ``asset_id`` and ``failure_date_column`` columns.
        failure_date_column:
            Column in the failures CSV that holds the failure date
            (default ``"machine_initialisation_date"``).
        failure_date_format:
            Format of the failure date column. ``'infer'`` (default) tries
            ``dayfirst=True`` first then falls back to auto-detection.
            Pass a strftime string (e.g. ``'%d/%m/%Y'``) to parse explicitly.
        prediction_horizon_days:
            Number of days before a failure to label as positive (default 14).
        exclusion_days_after:
            Number of days after a failure to exclude from training (recovery period, default 7).
        target_imbalance_ratio:
            Maximum ratio of negatives to positives after downsampling (default 10).
            ``None`` keeps all negatives.
        sampling_strategy:
            How negatives are downsampled: ``"block"`` preserves temporal structure,
            ``"random"`` samples individual rows (default ``"block"``).
        block_size_days:
            Calendar-day block size for block-based downsampling (default 14).
        n_candidates:
            Number of threshold candidates to evaluate per subsystem (default 200).
        fallback_quantile:
            Quantile used as fallback when a subsystem has too few positives (default 0.95).
        min_positives:
            Minimum positive rows required to attempt AUC training per subsystem (default 5).
        lr_c:
            Logistic regression regularisation strength C (default 0.5).
        timeout:
            Maximum seconds to wait for upload and validation (default 600 s).

        Returns:
            Dict with ``message``, ``row_count``, ``asset_count``, ``is_free_text``,
            ``supervised``, ``next_step``, and your full configuration echoed back
            (``file_path``, ``asset_id_column``, ``timestamp_column``,
            ``rolling_window``, ``rolling_feature_type``, ``quantile_for_thresholds``,
            ``sheet_name``, ``failures_path``).
        """
        _v.validate_configure_training(
            file_path=file_path,
            asset_id_column=asset_id_column,
            timestamp_column=timestamp_column,
            rolling_window=rolling_window,
            rolling_feature_type=rolling_feature_type,
            quantile_for_thresholds=quantile_for_thresholds,
            sheet_name=sheet_name,
            supervised=supervised,
            failures_path=failures_path,
            failure_date_column=failure_date_column,
            sampling_strategy=sampling_strategy,
            prediction_horizon_days=prediction_horizon_days,
            exclusion_days_after=exclusion_days_after,
            target_imbalance_ratio=target_imbalance_ratio,
            block_size_days=block_size_days,
            n_candidates=n_candidates,
            fallback_quantile=fallback_quantile,
            min_positives=min_positives,
            lr_c=lr_c,
        )
        data = {
            "auth_id":                 self._auth_id,
            "asset_id_column":         asset_id_column,
            "timestamp_column":        timestamp_column,
            "date_format":             date_format,
            "rolling_window":          str(rolling_window),
            "rolling_feature_type":    rolling_feature_type,
            "quantile_for_thresholds": str(quantile_for_thresholds),
            "supervised":              str(supervised).lower(),
            "failure_date_column":     failure_date_column,
            "failure_date_format":     failure_date_format,
            "prediction_horizon_days": str(prediction_horizon_days),
            "exclusion_days_after":    str(exclusion_days_after),
            "sampling_strategy":       sampling_strategy,
            "block_size_days":         str(block_size_days),
            "n_candidates":            str(n_candidates),
            "fallback_quantile":       str(fallback_quantile),
            "min_positives":           str(min_positives),
            "lr_c":                    str(lr_c),
        }
        if target_imbalance_ratio is not None:
            data["target_imbalance_ratio"] = str(target_imbalance_ratio)
        if sheet_name:
            data["sheet_name"] = sheet_name

        def _call():
            with open(file_path, "rb") as fh:
                filename = os.path.basename(file_path)
                files: list = [("file", (filename, fh))]
                if supervised and failures_path:
                    ff = open(failures_path, "rb")  # noqa: WPS515
                    files.append(("failures_file", (os.path.basename(failures_path), ff)))
                try:
                    return self._http.post(
                        "/v1/risk-score/configure-training",
                        data=data,
                        files=files,
                        timeout=timeout,
                    )
                finally:
                    if supervised and failures_path:
                        ff.close()

        raw = self._run_blocking("configure_training", _call)
        result = {
            **raw,
            "auth_id":                 self._auth_id,
            "file_path":               os.path.abspath(file_path),
            "asset_id_column":         asset_id_column,
            "timestamp_column":        timestamp_column,
            "date_format":             date_format,
            "rolling_window":          rolling_window,
            "rolling_feature_type":    rolling_feature_type,
            "quantile_for_thresholds": quantile_for_thresholds,
            "sheet_name":              sheet_name,
            "supervised":              supervised,
            "failures_path":           os.path.abspath(failures_path) if failures_path else None,
        }
        self._save_artifact("configure_training", result)
        return result

    # ------------------------------------------------------------------ #
    # Risk Score — Step 10: train_risk_model  (background)
    # Re-runnable until Step 11 (configure_generation) starts.
    # ------------------------------------------------------------------ #

    def train_risk_model(
        self,
        *,
        timeout: float = 3600.0,
    ) -> Dict[str, Any]:
        """
        Train the risk score model — calibrates per-subsystem thresholds from
        the training dataset uploaded in ``configure_training``.

        Blocks until training is complete, then saves the result to
        ``{artifact_dir}/train_risk_model.json``.

        The result includes ``thresholds_path`` (path to ``calibration_thresholds.json``
        in ``artifact_dir``) so you can inspect thresholds immediately:

        .. code-block:: python

            result = session.train_risk_model()
            import json
            with open(result["thresholds_path"]) as f:
                thresholds = json.load(f)
            # {"motion_control-datum_control": 3.0, ...}

        Args:
            timeout:
                Maximum seconds to wait for training to complete (default 1 h).

        Returns:
            Dict with ``auth_id``, ``subsystems_calibrated``, ``supervised``,
            ``baseline_auc_roc``, ``supervised_auc_roc``.  When ``artifact_dir``
            is set, also includes ``thresholds_path``, ``training_fe_path``,
            ``training_scores_path``; fixed-log sessions add ``logs_mapping_path``;
            import_model sessions add ``model_config_path``; supervised sessions
            add ``trained_weights_path`` and ``supervised_report_path``.
        """
        raw = self._run_blocking(
            "run_training",
            lambda: self._http.post(
                "/v1/risk-score/run-training",
                params={"auth_id": self._auth_id},
                timeout=timeout,
            ),
        )
        result: Dict[str, Any] = {
            "auth_id":               self._auth_id,
            "subsystems_calibrated": raw.get("subsystems_calibrated", 0),
            "supervised":            raw.get("supervised", False),
            "baseline_auc_roc":      raw.get("baseline_auc_roc"),
            "supervised_auc_roc":    raw.get("supervised_auc_roc"),
        }

        # Download training artifacts into artifact_dir immediately so the user can
        # inspect them without waiting for run_generation.
        # Only attempt downloads that apply to this session type — avoids noisy
        # 422/500 errors in the backend log for files that were never produced.
        if self._artifact_dir:
            os.makedirs(self._artifact_dir, exist_ok=True)

            # Fetch session state once to determine which optional downloads apply.
            try:
                _status = self._http.get(f"/v1/sessions/{self._auth_id}/status")
                _steps  = _status.get("steps", {})
            except Exception:
                _steps = {}

            _supervised        = _steps.get("train_risk_model", {}).get("supervised", False)
            _is_free_text      = _steps.get("configure_labelling_pipeline", {}).get("is_free_text", True)
            _import_model_done = _steps.get("import_model", {}).get("state") == "DONE"

            # Always produced for every session.
            downloads = [
                (
                    "calibration_thresholds.json",
                    "/v1/risk-score/download-thresholds",
                    "thresholds_path",
                ),
                (
                    "training_fe.parquet",
                    "/v1/risk-score/download-training-fe",
                    "training_fe_path",
                ),
                (
                    "training_scores.parquet",
                    "/v1/risk-score/download-training-scores",
                    "training_scores_path",
                ),
            ]

            # Only for fixed-log (is_free_text=False) sessions.
            if not _is_free_text:
                downloads.append((
                    "logs_by_system_subsystem.json",
                    "/v1/risk-score/download-logs-mapping",
                    "logs_mapping_path",
                ))

            # Only when the risk-score session was started via import_model().
            if _import_model_done:
                downloads.append((
                    "model_config.json",
                    "/v1/risk-score/download-model-config",
                    "model_config_path",
                ))

            # Only when configure_training(supervised=True) was used.
            if _supervised:
                downloads.extend([
                    (
                        "trained_weights.json",
                        "/v1/risk-score/download-trained-weights",
                        "trained_weights_path",
                    ),
                    (
                        "supervised_training_report.json",
                        "/v1/risk-score/download-supervised-report",
                        "supervised_report_path",
                    ),
                ])

            for filename, endpoint, result_key in downloads:
                try:
                    full_url = f"{self._http._client.base_url}{endpoint}"
                    dest = os.path.join(self._artifact_dir, filename)
                    with self._http._client.stream(
                        "GET", full_url, params={"auth_id": self._auth_id}
                    ) as r:
                        if r.is_success:
                            with open(dest, "wb") as fh:
                                for chunk in r.iter_bytes(chunk_size=65536):
                                    fh.write(chunk)
                            result[result_key] = os.path.abspath(dest)
                except Exception:
                    pass  # best-effort; artifacts still available in the final zip

        self._save_artifact("train_risk_model", result)
        return result

    # Keep old name as an alias for backward compatibility
    def run_training(self, *args, **kwargs) -> Dict[str, Any]:
        """Alias for ``train_risk_model()`` — kept for backward compatibility."""
        return self.train_risk_model(*args, **kwargs)

    # ------------------------------------------------------------------ #
    # Risk Score — Step 11: configure_generation
    # Re-runnable until Step 12 (run_generation) starts.
    # ------------------------------------------------------------------ #

    def configure_generation(
        self,
        file_path: str,
        date_format: str = "infer",
        sheet_name: Optional[str] = None,
        weights_source: str = "labelling",
        *,
        timeout: float = 600.0,
    ) -> Dict[str, Any]:
        """
        Upload the logs to score and lock the generation configuration.

        This is Step 11.  The file must have the same column structure as the
        training dataset — it goes through the same classification pipeline.
        Can be a new batch of operational logs or the same dataset used for training.

        Can be re-run until Step 12 (generate_risk_scores) starts.

        Args:
            file_path:
                Path to the log file to score (.csv or .xlsx).
            date_format:
                ``'infer'`` auto-detects the date format.  Pass a strftime string if needed.
            sheet_name:
                XLSX only.  ``None`` auto-detects the first sheet.
            weights_source:
                Which weights to use for risk score generation.
                ``"labelling"`` (default) uses the expert weights from the labelling step.
                ``"supervised"`` uses the weights trained via logistic regression —
                only valid after ``configure_training(supervised=True)`` + ``train_risk_model()``.
            timeout:
                Maximum seconds to wait for upload (default 600 s).

        Returns:
            Dict with ``message``, ``row_count``, ``asset_count``, ``weights_source``,
            ``next_step``, and your configuration echoed back (``file_path``,
            ``date_format``, ``sheet_name``, ``weights_source``).
        """
        _v.validate_configure_generation(
            file_path=file_path,
            sheet_name=sheet_name,
            weights_source=weights_source,
        )
        data: Dict[str, str] = {
            "auth_id":        self._auth_id,
            "date_format":    date_format,
            "weights_source": weights_source,
        }
        if sheet_name:
            data["sheet_name"] = sheet_name

        def _call():
            with open(file_path, "rb") as fh:
                filename = os.path.basename(file_path)
                return self._http.post(
                    "/v1/risk-score/configure-generation",
                    data=data,
                    files={"file": (filename, fh)},
                    timeout=timeout,
                )

        raw = self._run_blocking("configure_generation", _call)
        result = {
            **raw,
            "auth_id":        self._auth_id,
            "file_path":      os.path.abspath(file_path),
            "date_format":    date_format,
            "sheet_name":     sheet_name,
            "weights_source": weights_source,
        }
        self._save_artifact("configure_generation", result)
        return result

    # ------------------------------------------------------------------ #
    # Risk Score — Step 12: generate_risk_scores  (one-way door)
    # ------------------------------------------------------------------ #

    def generate_risk_scores(
        self,
        dest_dir: str,
        *,
        timeout: float = 3600.0,
    ) -> Dict[str, Any]:
        """
        Generate risk scores for every asset in the generation dataset.
        ONE-WAY DOOR — cannot be repeated on the same session.

        Blocks until complete, then automatically:
        1. Downloads ``complete_model_{auth_id}.zip`` to ``dest_dir``
        2. Extracts key artifacts into ``artifact_dir`` (if set)
        3. Wipes the session

        Extracted to ``artifact_dir``:

        - ``risk_scores.parquet`` → ``result["parquet_path"]``
        - ``classified_logs.parquet`` → ``result["classified_logs_path"]`` (free-text only)
        - ``logs_by_system_subsystem.json`` → ``result["logs_mapping_path"]``
        - ``calibration_thresholds.json`` → ``result["thresholds_path"]``
        - ``accepted_hierarchy.json`` → ``result["hierarchy_path"]``

        Args:
            dest_dir:
                Directory to save the zip into.  Created if it does not exist.
            timeout:
                Maximum seconds to wait for the server to finish (default 1 h).

        Returns:
            Dict with ``auth_id``, ``zip_path`` (absolute path of the complete model zip),
            ``dest_dir``, ``assets_scored``, ``date_range``.  When ``artifact_dir``
            is set, also includes ``parquet_path`` (risk_scores.parquet),
            ``logs_mapping_path``, ``thresholds_path``, ``hierarchy_path``,
            ``model_config_path``; free-text sessions add ``classified_logs_path``.
        """
        os.makedirs(dest_dir, exist_ok=True)
        raw = self._run_blocking(
            "run_generation",
            lambda: self._http.post(
                "/v1/risk-score/run-generation",
                params={"auth_id": self._auth_id},
                timeout=timeout,
            ),
        )
        dest_path = os.path.join(dest_dir, f"complete_model_{self._auth_id}.zip")
        abs_path = self._download_and_wipe("/v1/risk-score/download-zip", dest_path)

        result: Dict[str, Any] = {
            "auth_id":       self._auth_id,
            "zip_path":      abs_path,
            "dest_dir":      os.path.abspath(dest_dir),
            "assets_scored": raw.get("assets_scored", 0),
            "date_range":    raw.get("date_range"),
        }

        # Extract key artifacts into artifact_dir for quick access
        if self._artifact_dir:
            os.makedirs(self._artifact_dir, exist_ok=True)
            try:
                with zipfile.ZipFile(abs_path) as zf:
                    names = zf.namelist()
                    extract_map = {
                        "risk_scores.parquet":            "parquet_path",
                        "classified_logs.parquet":        "classified_logs_path",
                        "logs_by_system_subsystem.json":  "logs_mapping_path",
                        "calibration_thresholds.json":    "thresholds_path",
                        "accepted_hierarchy.json":        "hierarchy_path",
                        "model_config.json":              "model_config_path",
                    }
                    for filename, result_key in extract_map.items():
                        entry = next((n for n in names if n.endswith(filename)), None)
                        if entry:
                            dest = os.path.join(self._artifact_dir, filename)
                            with zf.open(entry) as src, open(dest, "wb") as dst:
                                dst.write(src.read())
                            result[result_key] = os.path.abspath(dest)
            except Exception:
                pass  # zip is intact — extraction is best-effort

        self._save_artifact("generate_risk_scores", result)
        return result

    # Keep old name as an alias for backward compatibility
    def run_generation(self, *args, **kwargs) -> Dict[str, Any]:
        """Alias for ``generate_risk_scores()`` — kept for backward compatibility."""
        return self.generate_risk_scores(*args, **kwargs)

    # ------------------------------------------------------------------ #

    def __repr__(self) -> str:
        return f"Session(auth_id={self._auth_id!r})"
