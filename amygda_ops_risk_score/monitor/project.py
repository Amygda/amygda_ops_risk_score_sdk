"""The risk monitor folder and its runs. See the package docstring for layout."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

import pandas as pd

from amygda_ops_risk_score.monitor import store as storage

CONFIG = "monitor.json"
BUNDLE = "bundle.zip"
LOCK = "monitor.lock"
# How many logs of each kind every asset had in every scored period, kept
# for the dashboard's "Logs behind the score" panel. The raw-log history is
# only kept as far back as scoring needs it; this is kept for longer.
LOG_COUNTS = "log_counts.parquet"
# Free-text models: each log's system and subsystem, as the API matched it.
LOG_MAP = "log_map.parquet"
LOG_DAYS = 180
FORMAT_VERSION = 1
INPUT_TYPES = (".csv", ".xlsx", ".xls", ".parquet")
DEFAULT_KEY_ENV = "AMYGDA_API_KEY"
# Rows per score call. The API allows 5,000 for free-text and 1M for fixed-log;
# the fixed-log figure is kept lower so each upload stays well under 30 MB.
MAX_ROWS_FREE_TEXT = 5000
MAX_ROWS_FIXED = 400_000
# Unmatched-log warnings: almost nothing matched, or a clear rise on the share
# the first run saw (some logs never match, and how many depends on the model).
UNMATCHED_ALL = 0.95
UNMATCHED_RISE = 0.15
# A model whose training logs leave more than this unmapped gets a warning at init.
UNMAPPED_WARN = 0.05
TRIGGERS = ("manual", "scheduled")
# How long to wait for the hosted API to start (it scales to zero when idle).
WAKE_TIMEOUT = 900.0

PathLike = Union[str, os.PathLike]


class MonitorError(Exception):
    """A monitor operation could not be completed (nothing was changed)."""


@dataclass
class RunResult:
    """What one ``Monitor.run`` did. Also saved as ``runs/<run_id>/run.json``."""

    run_id: str
    status: str  # ok | no_new_data | failed
    record: Dict[str, Any] = field(default_factory=dict)

    @property
    def warnings(self) -> List[str]:
        return self.record.get("warnings", [])

    def __repr__(self) -> str:
        r = self.record
        if self.status == "failed":
            return f"RunResult({self.run_id}, failed: {r.get('reason')})"
        if self.status != "ok":
            n = len(self.warnings)
            return f"RunResult({self.run_id}, {self.status}, warnings={n})"
        return (
            f"RunResult({self.run_id}, rows_new={r.get('rows_new')}, "
            f"periods={r.get('periods_upserted')}, assets={r.get('assets_in_batch')}, "
            f"warnings={len(self.warnings)})"
        )


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _run_id() -> str:
    return _now().strftime("%Y%m%dT%H%M%S%fZ")[:-4] + "Z"


def _write_json(path: Path, obj: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, default=str))
    os.replace(tmp, path)


def _write_parquet(path: Path, df: pd.DataFrame) -> None:
    tmp = path.with_suffix(".tmp.parquet")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def _read_table(path: Path) -> pd.DataFrame:
    low = path.name.lower()
    if low.endswith(".parquet"):
        return pd.read_parquet(path)
    if low.endswith((".xlsx", ".xls")):
        return pd.read_excel(path)
    return pd.read_csv(path, low_memory=False)


def _parse_timestamps(values: pd.Series, date_format: str) -> pd.Series:
    """Parse timestamps the same way the API does."""
    if pd.api.types.is_datetime64_any_dtype(values):
        out = values
    elif date_format == "infer":
        out = pd.to_datetime(values, errors="coerce")
    else:
        out = pd.to_datetime(values, format=date_format, errors="coerce")
    if getattr(out.dt, "tz", None) is not None:
        out = out.dt.tz_convert("UTC").dt.tz_localize(None)
    return out


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _failure_reason(exc: BaseException, from_inbox: bool) -> str:
    """A plain-language reason for a failed run, for the run record and dashboard."""
    import httpx

    from amygda_ops_risk_score.exceptions import APIError

    after = (
        " The files stay in inbox/ and the next run picks them up."
        if from_inbox
        else " Nothing was changed: run it again."
    )
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        return (
            "The Amygda API didn't respond in time (it may have been starting up, "
            "or the network is down)." + after
        )
    if isinstance(exc, (httpx.ConnectError, ConnectionError)):
        return "Couldn't connect to the Amygda API. Check the network." + after
    if isinstance(exc, APIError):
        if exc.status_code in (401, 403):
            return (
                "The API key was refused. Check the key in the environment "
                "variable the monitor reads (AMYGDA_API_KEY by default)." + after
            )
        if exc.status_code == 404:
            return (
                "The deployment no longer exists (deleted, or unused for 90 days). "
                "Create a new monitor with `amygda-risk init`."
            )
        return f"The API returned an error ({exc.status_code}): {exc.message}" + after
    if isinstance(exc, MonitorError):
        return str(exc)
    return f"Unexpected error ({type(exc).__name__}): {exc}" + after


def band_of(value: float, bands: Dict[str, Any]) -> str:
    if value >= bands["high"]:
        return "high"
    if value >= bands["watch"]:
        return "watch"
    return "normal"


_BAND_RANK = {"normal": 0, "watch": 1, "high": 2}


# ---------------------------------------------------------------------------
# Monitor
# ---------------------------------------------------------------------------


class Monitor:
    """A monitor folder tied to one deployment. Open an existing one with
    ``Monitor(path)``; create one with :meth:`Monitor.init`."""

    def __init__(self, path: PathLike, api_key: Optional[str] = None, client=None):
        self.path = Path(path).expanduser().resolve()
        if not (self.path / CONFIG).is_file():
            raise MonitorError(
                f"{self.path} is not a monitor folder (no {CONFIG}). "
                "Create one with Monitor.init(...) or `amygda-risk init`."
            )
        self.config: Dict[str, Any] = json.loads((self.path / CONFIG).read_text())
        if self.config.get("format") != FORMAT_VERSION:
            raise MonitorError(f"Unsupported monitor format in {CONFIG}.")
        try:
            self.store = storage.open_store(
                self.path, self.config.get("storage", "files")
            )
            self.store.check()
        except storage.StoreError as exc:
            raise MonitorError(str(exc)) from None
        self._api_key = api_key
        self._client = client

    # ------------------------------------------------------------------ #
    # Create
    # ------------------------------------------------------------------ #

    @classmethod
    def init(
        cls,
        path: PathLike,
        *,
        model: Optional[PathLike] = None,
        deployment_id: Optional[str] = None,
        name: Optional[str] = None,
        accept_storage: Optional[bool] = None,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        api_key_env: str = DEFAULT_KEY_ENV,
        fleet_name: Optional[str] = None,
        bands: Optional[Dict[str, float]] = None,
        history: Optional[Union[PathLike, pd.DataFrame]] = None,
        date_format: Optional[str] = None,
        storage_kind: str = "files",
        client=None,
    ) -> "Monitor":
        """Create a monitor folder and deploy the model (or attach to a deployment).

        Args:
            path: New folder for the monitor (must not already be a monitor).
            model: ``complete_model_<id>.zip``. The bundle is built here, saved
                as ``bundle.zip`` and deployed. Needs ``name``. For a fixed-log
                model, log codes the model maps to no subsystem are listed in
                ``monitor.json`` (``model_checks``); see :meth:`model_warnings`.
            deployment_id: Use an existing deployment instead of ``model``.
            accept_storage: No longer needed; accepted and ignored.
            api_key: Your API key. Not saved: later runs read it from the
                ``api_key_env`` environment variable (default ``AMYGDA_API_KEY``)
                or from ``Monitor(path, api_key=...)``.
            api_url: API to use. Defaults to the hosted API.
            fleet_name: Shown on the dashboard, e.g. "Conveyor fleet".
            bands: ``{"watch": 35, "high": 40}``, e.g. the levels agreed when
                the model was checked. If left out, they are set from the
                model's training scores (95th and 99th percentile). Without a
                model zip (``deployment_id`` or a bare bundle), the first run
                sets provisional ones from its own scores. Either way they stay
                fixed after that, so runs can be compared.
            history: Earlier logs (e.g. the training file) to use as history,
                so the first run's rolling features are complete.
            date_format: Timestamp format of your files. Defaults to the one
                saved with the model.
            storage_kind: Where scores, run records and alerts are kept:
                ``"files"`` (parquet and JSON files, the default) or
                ``"sqlite"`` (one database file, ``monitor.db``). Change it
                later with :meth:`set_storage`.
        """
        path = Path(path).expanduser().resolve()
        if (path / CONFIG).exists():
            raise MonitorError(
                f"{path} is already a monitor. Open it with Monitor(path)."
            )
        if path.exists() and any(path.iterdir()):
            raise MonitorError(f"{path} exists and is not empty. Pick a new folder.")
        if bool(model) == bool(deployment_id):
            raise MonitorError(
                "Pass either model (to deploy) or deployment_id (existing)."
            )
        if bands is not None:
            _check_bands(bands)
        if storage_kind not in storage.KINDS:
            raise MonitorError(f"storage must be one of: {', '.join(storage.KINDS)}.")
        key = api_key or os.environ.get(api_key_env)
        if not key:
            raise MonitorError(f"No API key: pass api_key or set {api_key_env}.")

        from amygda_ops_risk_score import OpsRiskClient
        from amygda_ops_risk_score.deployment import (
            build_scoring_bundle,
            is_scoring_bundle,
            unmapped_codes,
        )

        if model and not name:
            raise MonitorError("name is required when deploying a model.")
        if client is None:
            client = OpsRiskClient(api_url)
            client.wait_until_ready(timeout=WAKE_TIMEOUT)
        path.mkdir(parents=True, exist_ok=True)
        checks: Dict[str, Any] = {}
        try:
            if model:
                bundle = path / BUNDLE
                if is_scoring_bundle(str(model)):
                    shutil.copyfile(model, bundle)
                else:
                    build_scoring_bundle(str(model), str(bundle))
                    if bands is None:
                        bands = _bands_from_training(model)
                    unmapped = unmapped_codes(str(model))
                    if unmapped is not None:
                        checks["unmapped_codes"] = unmapped
                dep = client.deploy_model(key, str(bundle), name)
            else:
                dep = client.get_deployment(key, deployment_id)
            for sub in ("history", "dashboard", "inbox"):
                (path / sub).mkdir(exist_ok=True)
            store = storage.open_store(path, storage_kind)
            store.prepare()
            config = {
                "format": FORMAT_VERSION,
                "storage": storage_kind,
                "created_at": _now().isoformat(timespec="seconds"),
                "fleet_name": fleet_name or dep["name"],
                "api_url": api_url,
                "api_key_env": api_key_env,
                "deployment": {
                    k: dep.get(k)
                    for k in (
                        "deployment_id",
                        "name",
                        "is_free_text",
                        "log_column",
                        "asset_id_column",
                        "timestamp_column",
                        "date_format",
                        "rolling_window",
                        "rolling_feature_type",
                        "feature_frequency",
                        "weights_source",
                        "lookback_seconds",
                        "bundle_hash",
                    )
                },
                "date_format": date_format,
                "bands": dict(
                    bands, basis=bands.get("basis", "Set when the monitor was created.")
                )
                if bands
                else None,
                "dashboard_days": 90,
                "model_checks": checks,
            }
            _write_json(path / CONFIG, config)
            store.save_state({"known_assets": {}, "latest_timestamp": None, "runs": 0})
        except BaseException:
            shutil.rmtree(path, ignore_errors=True)
            raise

        mon = cls(path, api_key=key, client=client)
        if history is not None:
            mon.seed_history(history)
        return mon

    # ------------------------------------------------------------------ #
    # Properties
    # ------------------------------------------------------------------ #

    @property
    def deployment(self) -> Dict[str, Any]:
        return self.config["deployment"]

    @property
    def title(self) -> str:
        """The name at the top of the page: the layout's title when it has
        one, otherwise the fleet name followed by "risk"."""
        try:
            title = self.spec()["title"]
        except Exception:  # noqa: BLE001 - a broken layout still has a name
            title = None
        return title or f"{self.config['fleet_name']} risk"

    @property
    def columns(self) -> Dict[str, str]:
        d = self.deployment
        return {
            "asset": d["asset_id_column"],
            "ts": d["timestamp_column"],
            "log": d["log_column"],
        }

    @property
    def lookback(self) -> pd.Timedelta:
        return pd.Timedelta(seconds=self.deployment["lookback_seconds"])

    @property
    def frequency(self) -> pd.Timedelta:
        return pd.Timedelta(self.deployment["feature_frequency"])

    @property
    def keep_history(self) -> pd.Timedelta:
        # Lookback, plus the same again so data arriving a little late can
        # still be scored with full history.
        return self.lookback * 2

    @property
    def date_format(self) -> str:
        return (
            self.config.get("date_format")
            or self.deployment.get("date_format")
            or "infer"
        )

    def _state(self) -> Dict[str, Any]:
        return self.store.state()

    def _client_and_key(self):
        from amygda_ops_risk_score import OpsRiskClient

        key = self._api_key or os.environ.get(
            self.config.get("api_key_env", DEFAULT_KEY_ENV)
        )
        if not key:
            raise MonitorError(
                f"No API key: set {self.config.get('api_key_env', DEFAULT_KEY_ENV)} "
                "or open the monitor with Monitor(path, api_key=...)."
            )
        if self._client is None:
            client = OpsRiskClient(self.config.get("api_url"))
            # The hosted API scales to zero: wait for it before the first call,
            # so a scheduled run doesn't fail on a cold start.
            client.wait_until_ready(timeout=WAKE_TIMEOUT)
            self._client = client
        return self._client, key

    def model_warnings(self) -> List[str]:
        """Things to know about the deployed model, found when the monitor was
        created (e.g. common log codes that map to no subsystem)."""
        out = []
        u = (self.config.get("model_checks") or {}).get("unmapped_codes")
        if u and u["unmapped_share"] > UNMAPPED_WARN:
            top = ", ".join(f"{c['code']} ({c['share']:.1%})" for c in u["top"][:5])
            out.append(
                f"{u['unmapped_share']:.0%} of the training logs have codes the model "
                f"maps to no subsystem ({u['unmapped_code_count']} codes), so they add "
                f"nothing to any score. Most common: {top}. If any of these matter, "
                "add them to the hierarchy and retrain."
            )
        return out

    # ------------------------------------------------------------------ #
    # Reading logs
    # ------------------------------------------------------------------ #

    def _load_logs(self, sources: Iterable[Union[PathLike, pd.DataFrame]]) -> tuple:
        """Read inputs into the model's three columns, parsed. Returns
        ``(logs, counts, files)``."""
        cols = self.columns
        frames, files = [], []
        for src in sources:
            if isinstance(src, pd.DataFrame):
                frames.append(src)
                files.append("<DataFrame>")
                continue
            p = Path(src).expanduser()
            if not p.is_file():
                raise MonitorError(f"Input file not found: {p}")
            if not p.name.lower().endswith(INPUT_TYPES):
                raise MonitorError(
                    f"Unsupported file type: {p.name} (use {', '.join(INPUT_TYPES)})"
                )
            frames.append(_read_table(p))
            files.append(str(p))
        if not frames:
            return self._empty_logs(), {"rows_read": 0}, files

        out = []
        for df, name in zip(frames, files):
            missing = [c for c in cols.values() if c not in df.columns]
            if missing:
                raise MonitorError(
                    f"{name} is missing column(s) {missing} that the model was trained "
                    f"with. Columns found: {list(df.columns)[:20]}"
                )
            part = df[list(dict.fromkeys(cols.values()))].copy()
            parsed = _parse_timestamps(part[cols["ts"]], self.date_format)
            if len(part) and parsed.isna().all():
                # A whole file with no readable timestamp is almost always the
                # wrong date format; stop rather than skip it quietly.
                sample = part[cols["ts"]].dropna().astype(str).head(3).tolist()
                raise MonitorError(
                    f"No timestamp in {name} could be read with the format "
                    f"'{self.date_format}' (e.g. {sample}). Set the right format with "
                    '`date_format` in monitor.json, e.g. "infer" or "%Y-%m-%d %H:%M".'
                )
            part[cols["ts"]] = parsed
            out.append(part)
        logs = pd.concat(out, ignore_index=True)
        rows_read = len(logs)
        logs = logs.dropna(subset=[cols["asset"], cols["ts"]])
        logs[cols["asset"]] = logs[cols["asset"]].astype(str)
        dropped = rows_read - len(logs)
        return (
            logs.reset_index(drop=True),
            {"rows_read": rows_read, "rows_unreadable": dropped},
            files,
        )

    def _empty_logs(self) -> pd.DataFrame:
        c = self.columns
        return pd.DataFrame(
            {
                c["asset"]: pd.Series(dtype=str),
                c["ts"]: pd.Series(dtype="datetime64[ns]"),
                c["log"]: pd.Series(dtype=object),
            }
        )

    def _history(self) -> pd.DataFrame:
        p = self.path / "history" / "logs.parquet"
        return pd.read_parquet(p) if p.exists() else self._empty_logs()

    def seed_history(self, source: Union[PathLike, pd.DataFrame]) -> int:
        """Use earlier logs as history (keeps only the most recent stretch needed).
        Returns the number of rows kept."""
        logs, _, _ = self._load_logs([source])
        ts = self.columns["ts"]
        hist = pd.concat([self._history(), logs], ignore_index=True)
        if len(hist):
            latest = hist[ts].max()
            hist = hist[hist[ts] >= latest - self.keep_history]
        hist = hist.sort_values([self.columns["asset"], ts]).reset_index(drop=True)
        _write_parquet(self.path / "history" / "logs.parquet", hist)
        return len(hist)

    def _remove_known(self, new: pd.DataFrame, hist: pd.DataFrame) -> tuple:
        """Drop rows already in history (re-sent files, overlapping exports).
        Repeats within a file are kept: a code logged twice counts twice."""
        if not len(hist) or not len(new):
            return new, 0
        keys = list(self.columns.values())

        def with_occurrence(df):
            k = df[keys].astype(str)
            return k.assign(_n=k.groupby(keys).cumcount())

        seen = pd.MultiIndex.from_frame(with_occurrence(hist))
        mine = pd.MultiIndex.from_frame(with_occurrence(new))
        dup = mine.isin(seen)
        return new[~dup].reset_index(drop=True), int(dup.sum())

    # ------------------------------------------------------------------ #
    # Scoring
    # ------------------------------------------------------------------ #

    def _max_rows(self) -> int:
        return MAX_ROWS_FREE_TEXT if self.deployment["is_free_text"] else MAX_ROWS_FIXED

    def _slices(self, logs: pd.DataFrame, start: pd.Timestamp) -> List[tuple]:
        """Split the period from ``start`` into calls that each fit the row
        limit, including their own lookback of history."""
        ts = logs[self.columns["ts"]].sort_values().reset_index(drop=True)
        end_all = ts.iloc[-1] + pd.Timedelta(seconds=1)
        limit, lb, freq = self._max_rows(), self.lookback, self.frequency
        out, s = [], start
        while s < end_all:
            lo = ts.searchsorted(s - lb, side="left")
            if ts.searchsorted(end_all, side="left") - lo <= limit:
                out.append((s, end_all))
                break
            # Largest end with at most `limit` rows in [s - lookback, end).
            end = ts.iloc[min(lo + limit, len(ts) - 1)]
            end = end.floor(freq)
            if end <= s:
                raise MonitorError(
                    f"Too many logs to score: one {freq} period plus its {lb} of "
                    "history "
                    f"is over the {limit:,}-row limit per call."
                )
            out.append((s, end))
            s = end
        return out

    def _score(self, logs: pd.DataFrame, start: Optional[pd.Timestamp]) -> tuple:
        """Score ``logs`` (history + new) from ``start``. Returns
        ``(scores, diagnostics_list, log_map)``; ``log_map`` is each free-text
        log's system and subsystem (``log``, ``system``, ``subsystem``), or
        None for fixed-log models and older APIs."""
        client, key = self._client_and_key()
        ts = self.columns["ts"]
        dep_id = self.deployment["deployment_id"]
        first = start if start is not None else logs[ts].min()
        parts, diags, maps = [], [], []
        for s, e in self._slices(logs, first):
            window = logs[(logs[ts] >= s - self.lookback) & (logs[ts] < e)]
            res = client.score(
                key,
                dep_id,
                window,
                score_from=s if start is not None or s != first else None,
                date_format="infer",  # timestamps are already parsed
            )
            parts.append(res.scores)
            diags.append(res.diagnostics)
            if getattr(res, "log_map", None) is not None:
                maps.append(res.log_map)
        scores = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
        if len(scores):
            scores["period_start"] = pd.to_datetime(scores["period_start"])
            scores = scores.drop_duplicates(["asset_id", "period_start"], keep="last")
        log_map = (
            pd.concat(maps, ignore_index=True).drop_duplicates("log", keep="last")
            if maps
            else None
        )
        return scores.reset_index(drop=True), diags, log_map

    # ------------------------------------------------------------------ #
    # Run
    # ------------------------------------------------------------------ #

    def _acquire_lock(self) -> Path:
        lock = self.path / LOCK
        if lock.exists():
            try:
                info = json.loads(lock.read_text())
                if _pid_alive(int(info.get("pid", -1))):
                    raise MonitorError(
                        f"Another run is in progress (pid {info['pid']}, started "
                        f"{info.get('started_at')}). New files wait in inbox/."
                    )
            except (ValueError, OSError):
                pass
            lock.unlink(missing_ok=True)  # stale: the run that held it has gone
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise MonitorError("Another run started at the same moment. Try again.")
        with os.fdopen(fd, "w") as f:
            json.dump({"pid": os.getpid(), "started_at": _now().isoformat()}, f)
        return lock

    def inbox_files(self) -> List[Path]:
        inbox = self.path / "inbox"
        files = [
            p
            for p in inbox.iterdir()
            if p.is_file() and p.name.lower().endswith(INPUT_TYPES)
        ]
        return sorted(files, key=lambda p: (p.stat().st_mtime, p.name))

    def run(
        self,
        inputs: Optional[
            Union[PathLike, pd.DataFrame, List[Union[PathLike, pd.DataFrame]]]
        ] = None,
        dashboard: bool = True,
        trigger: str = "manual",
    ) -> RunResult:
        """Score new data and merge it into the monitor.

        Args:
            inputs: File(s) or DataFrame(s) of new logs. If left out, every file
                in ``inbox/`` is used and moved to ``inbox/processed/`` afterwards.
            dashboard: Rebuild ``dashboard/index.html`` after the run.
            trigger: ``"manual"`` or ``"scheduled"``, saved with the run
                (the fleet app's schedule passes ``"scheduled"``).

        If the run fails, a run record with ``status: "failed"`` and a
        plain-language ``reason`` is saved, the dashboard shows it, and the
        error is raised. Files in ``inbox/`` stay there for the next run.

        Steps: read and check the data; drop rows already seen; add
        ``lookback`` of history; score; merge scores by asset and period
        (re-scored periods replace older ones); mark the newest period
        provisional; trim history; save ``runs/<run_id>/run.json``.
        """
        if trigger not in TRIGGERS:
            raise MonitorError(f"trigger must be one of {TRIGGERS}.")
        lock = self._acquire_lock()
        run_id = _run_id()
        started = _now()
        from_inbox = inputs is None
        sources: list = []
        try:
            if from_inbox:
                sources = self.inbox_files()
            elif isinstance(inputs, (list, tuple)):
                sources = list(inputs)
            else:
                sources = [inputs]
            try:
                result = self._run(run_id, started, sources, trigger)
                self._update_alerts(result.record)
            except Exception as exc:
                reason = self._record_failure(
                    run_id, started, sources, trigger, exc, from_inbox
                )
                try:
                    exc.monitor_reason = reason  # for the command line
                except AttributeError:
                    pass
                raise
            if from_inbox and sources and result.status in ("ok", "no_new_data"):
                done = self.path / "inbox" / "processed" / run_id
                done.mkdir(parents=True, exist_ok=True)
                for p in sources:
                    shutil.move(str(p), done / Path(p).name)
            if dashboard and result.status == "ok":
                # The scores are saved already; a dashboard problem must not
                # undo or fail the run.
                try:
                    self.dashboard()
                except Exception as exc:  # noqa: BLE001
                    msg = f"The dashboard could not be rebuilt: {exc}"
                    result.record.setdefault("warnings", []).append(msg)
                    self._save_run(result.run_id, result.record)
            return result
        finally:
            lock.unlink(missing_ok=True)

    def _record_failure(
        self,
        run_id: str,
        started: datetime,
        sources: list,
        trigger: str,
        exc: BaseException,
        from_inbox: bool,
    ) -> str:
        """Save a failed run's record (nothing else was changed) and show it on
        the dashboard. Returns the reason. Never raises: the original error
        matters more."""
        reason = _failure_reason(exc, from_inbox)
        try:
            record = {
                "run_id": run_id,
                "status": "failed",
                "trigger": trigger,
                "started_at": started.isoformat(),
                "finished_at": _now().isoformat(),
                "inputs": [
                    "<DataFrame>" if isinstance(s, pd.DataFrame) else str(s)
                    for s in sources
                ],
                "reason": reason,
                "error": f"{type(exc).__name__}: {exc}"[:2000],
                "warnings": [],
            }
            self._save_run(run_id, record)
            self._update_alerts(record)
            if len(self._scores()):
                self.dashboard()
        except Exception:  # noqa: BLE001
            pass
        return reason

    # ------------------------------------------------------------------ #
    # Alerts
    # ------------------------------------------------------------------ #

    def _update_alerts(self, record: Dict[str, Any]) -> None:
        """Check the alert rules against a run that just ended. A problem
        here never fails the run: it is added to the run's warnings."""
        from amygda_ops_risk_score.monitor import alerts as alerting

        try:
            rules = self.spec()["alerts"]["rules"]
            if not rules:
                return
            failed = 0
            for r in reversed(self.runs()):
                if r.get("status") != "failed":
                    break
                failed += 1
            findings, checked = alerting.findings_for_run(
                rules, record, self._scores(), failed_in_a_row=failed
            )
            raised = alerting.AlertStore(self.store).apply(
                findings, checked, record["run_id"]
            )
            if raised and record.get("status") != "failed":
                record["alerts_raised"] = [a["id"] for a in raised]
                self._save_run(record["run_id"], record)
        except Exception as exc:  # noqa: BLE001
            if record.get("status") != "failed":
                record.setdefault("warnings", []).append(
                    f"The alert rules could not be checked: {exc}"
                )
                self._save_run(record["run_id"], record)

    def alerts(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Alerts, oldest first. ``status``: "open", "acknowledged" or
        "cleared" to list only those."""
        from amygda_ops_risk_score.monitor.alerts import AlertStore

        found = AlertStore(self.store).all()
        return [a for a in found if status in (None, a["status"])]

    def acknowledge_alerts(self, alert_id: Optional[str] = None) -> int:
        """Acknowledge one open alert by id, or every open alert. Returns how
        many were acknowledged."""
        from amygda_ops_risk_score.monitor.alerts import AlertStore

        n = AlertStore(self.store).acknowledge(alert_id)
        if alert_id and not n:
            raise MonitorError(f'There is no open alert "{alert_id}".')
        return n

    def _run(
        self, run_id: str, started: datetime, sources: list, trigger: str = "manual"
    ) -> RunResult:
        cols = self.columns
        ts, asset = cols["ts"], cols["asset"]
        state = self._state()
        warnings: List[str] = []
        record: Dict[str, Any] = {
            "run_id": run_id,
            "trigger": trigger,
            "started_at": started.isoformat(),
        }

        new, counts, files = self._load_logs(sources)
        record.update(inputs=files, **counts)
        hist = self._history()
        new, n_dup = self._remove_known(new, hist)
        record["rows_already_seen"] = n_dup

        # Rows older than the history kept here can't be scored with complete
        # history; scoring them would replace good scores with worse ones.
        if len(hist) and len(new):
            oldest_ok = hist[ts].min()
            too_old = new[ts] < oldest_ok
            record["rows_too_old"] = int(too_old.sum())
            if too_old.any():
                warnings.append(
                    f"{int(too_old.sum()):,} rows are older than the history kept here "
                    f"({oldest_ok:%Y-%m-%d %H:%M}) and were skipped. To include them, "
                    "re-score that period with `amygda-risk score`."
                )
                new = new[~too_old]
        else:
            record["rows_too_old"] = 0
        if counts.get("rows_unreadable"):
            warnings.append(
                f"{counts['rows_unreadable']:,} rows had no asset ID or a timestamp "
                "that "
                f"could not be read (format '{self.date_format}') and were skipped."
            )

        record["rows_new"] = len(new)
        if not len(new):
            record.update(
                status="no_new_data", warnings=warnings, finished_at=_now().isoformat()
            )
            self._save_run(run_id, record)
            return RunResult(run_id, "no_new_data", record)

        known = state.get("known_assets", {})
        batch_assets = sorted(new[asset].unique())
        new_assets = [a for a in batch_assets if a not in known]
        if known and new_assets:
            shown = ", ".join(new_assets[:10]) + (
                " ..." if len(new_assets) > 10 else ""
            )
            warnings.append(
                f"{len(new_assets)} asset(s) not seen before: {shown}. Their first "
                f"{self.lookback} have little history, so early scores may be low."
            )
        record.update(assets_in_batch=len(batch_assets), new_assets=new_assets)

        start = new[ts].min()
        all_logs = pd.concat([hist, new], ignore_index=True).sort_values([asset, ts])
        window = all_logs[all_logs[ts] >= start - self.lookback].reset_index(drop=True)
        record["new_period"] = {"start": str(start), "end": str(new[ts].max())}
        has_history = len(hist) > 0 and hist[ts].min() <= start - self.lookback
        if not has_history:
            warnings.append(
                f"Less than {self.lookback} of history before {start:%Y-%m-%d}: the "
                "first "
                "periods have incomplete rolling features and may score low. "
                "Seed history with earlier logs to avoid this."
            )

        scores, diags, log_map = self._score(window, start)
        record["score_calls"] = len(diags)
        # Unmatched share over the new logs only. APIs before 4.2.0 report it
        # only for everything sent (new logs plus the history before them).
        if diags and all("rows_new" in d for d in diags):
            rows_in = sum(d["rows_new"] for d in diags)
            matched = sum(d["rows_new_matched"] for d in diags)
            basis = "new"
        else:
            rows_in = sum(d.get("rows_in", 0) for d in diags)
            matched = sum(d.get("rows_matched", 0) for d in diags)
            basis = "window"
        share = round(1 - matched / rows_in, 4) if rows_in else None
        record.update(unmatched_share=share, unmatched_basis=basis)
        # Some logs never match (e.g. routine entries); what matters is a rise
        # against this model's usual share, set by the first run that scores.
        # A baseline measured the other way is replaced.
        if state.get("unmatched_baseline_basis", "window") != basis:
            state.pop("unmatched_baseline", None)
        baseline = state.get("unmatched_baseline")
        if share is not None and baseline is None:
            state["unmatched_baseline"] = share
            state["unmatched_baseline_basis"] = basis
        if share is not None and share >= UNMATCHED_ALL:
            warnings.append(
                f"{share:.0%} of logs matched no subsystem. Check the log column "
                "holds the same kind of codes or text as the training data."
            )
        elif (
            share is not None
            and baseline is not None
            and share > baseline + UNMATCHED_RISE
        ):
            warnings.append(
                f"{share:.0%} of logs matched no subsystem, up from {baseline:.0%} "
                "in the first run. The logs may use codes or wording the model "
                "never saw: check the export, and consider retraining."
            )

        # Bands: normally set at init. Without them, set provisional ones once,
        # from this first run, then keep them fixed.
        if not self.config.get("bands") and len(scores):
            self.config["bands"] = _bands_from(
                scores["operational_risk"], basis=_FIRST_RUN_BASIS
            )
            _write_json(self.path / CONFIG, self.config)
            warnings.append(
                "Provisional alert bands set from this run's scores: watch "
                f"{self.config['bands']['watch']}, "
                f"high {self.config['bands']['high']}. One run is a weak basis: set "
                "the levels agreed for this model in monitor.json."
            )
        bands = self.config.get("bands") or {"watch": 35.0, "high": 40.0}

        # Merge scores and mark the newest period provisional.
        all_hist = all_logs[all_logs[ts] >= all_logs[ts].max() - self.keep_history]
        latest = all_logs[ts].max()
        before = self._scores()
        merged, changes = self._merge(before, scores, run_id, latest, bands)
        self.store.save_scores(merged)
        # Counts for the logs panel: what is kept so far (or, the first time,
        # what the history holds) plus this run's new logs.
        try:
            kept = self.path / "history" / LOG_COUNTS
            base = _read_table(kept) if kept.is_file() else self._count_logs(hist)
            counts = pd.concat([base, self._count_logs(new)], ignore_index=True)
            counts = counts.groupby(
                ["asset_id", "period_start", "log"], as_index=False, sort=True
            )["n"].sum()
            oldest = counts["period_start"].max() - pd.Timedelta(days=LOG_DAYS)
            counts = counts[counts["period_start"] >= oldest]
            _write_parquet(kept, counts)
            if log_map is not None:
                self._keep_log_map(log_map, counts)
        except Exception as exc:  # noqa: BLE001 - the scores matter more
            warnings.append(f"The logs for the dashboard could not be kept: {exc}")
        _write_parquet(
            self.path / "history" / "logs.parquet", all_hist.reset_index(drop=True)
        )

        for a in batch_assets:
            known.setdefault(a, run_id)
        state.update(
            known_assets=known,
            latest_timestamp=str(latest),
            runs=state.get("runs", 0) + 1,
            last_run_id=run_id,
        )
        self.store.save_state(state)

        record.update(
            status="ok",
            periods_upserted=len(scores),
            provisional_periods=int(merged["provisional"].sum()),
            latest_timestamp=str(latest),
            bands={k: bands[k] for k in ("watch", "high")},
            bundle_hash=self.deployment.get("bundle_hash"),
            changes=changes,
            warnings=warnings,
            finished_at=_now().isoformat(),
        )
        self._save_run(run_id, record)
        return RunResult(run_id, "ok", record)

    def _merge(
        self,
        before: pd.DataFrame,
        scores: pd.DataFrame,
        run_id: str,
        latest: pd.Timestamp,
        bands: Dict[str, Any],
    ) -> tuple:
        key = ["asset_id", "period_start"]
        # Trend columns are normalised within each call, so values from
        # different runs can't be compared. They don't feed the risk scores.
        scores = scores.drop(columns=[c for c in scores.columns if "_trend" in c])
        scores = scores.assign(
            run_id=run_id, bundle_hash=self.deployment.get("bundle_hash")
        )
        if len(before):
            before = before.drop(columns=["provisional"], errors="ignore")
            merged = pd.concat([before, scores], ignore_index=True)
        else:
            merged = scores
        merged = (
            merged.drop_duplicates(key, keep="last")
            .sort_values(key)
            .reset_index(drop=True)
        )
        merged["provisional"] = merged["period_start"] + self.frequency > latest

        # What changed for each asset in this run.
        changes = []
        for a, rows in scores.groupby("asset_id"):
            prev = before[before["asset_id"] == a] if len(before) else before
            prev = (
                prev[prev["period_start"] < rows["period_start"].min()]
                if len(prev)
                else prev
            )
            prev_latest = (
                float(prev.sort_values("period_start")["operational_risk"].iloc[-1])
                if len(prev)
                else None
            )
            top = rows.loc[rows["operational_risk"].idxmax()]
            now_latest = float(
                rows.sort_values("period_start")["operational_risk"].iloc[-1]
            )
            changes.append(
                {
                    "asset_id": a,
                    "score_before_run": prev_latest,
                    "score_now": now_latest,
                    "change": round(now_latest - prev_latest, 2)
                    if prev_latest is not None
                    else None,
                    "highest_this_run": float(top["operational_risk"]),
                    "highest_this_run_at": str(top["period_start"]),
                    "band_before_run": band_of(prev_latest, bands)
                    if prev_latest is not None
                    else None,
                    "band_of_highest": band_of(float(top["operational_risk"]), bands),
                    "periods_scored": int(len(rows)),
                    "first_period": str(rows["period_start"].min()),
                    "last_period": str(rows["period_start"].max()),
                }
            )
        changes.sort(
            key=lambda c: (-_BAND_RANK[c["band_of_highest"]], -c["highest_this_run"])
        )
        return merged, changes

    def _save_run(self, run_id: str, record: Dict[str, Any]) -> None:
        self.store.save_run(run_id, record)

    # ------------------------------------------------------------------ #
    # Results
    # ------------------------------------------------------------------ #

    def _scores(self) -> pd.DataFrame:
        return self.store.scores()

    @property
    def scores(self) -> pd.DataFrame:
        """All scores so far: one row per asset and period."""
        return self._scores()

    def runs(self) -> List[Dict[str, Any]]:
        """Run records, oldest first."""
        return self.store.runs()

    def _count_logs(self, logs: pd.DataFrame) -> pd.DataFrame:
        """Logs as counts per asset, scored period and log."""
        cols = self.columns
        if not len(logs):
            return pd.DataFrame(columns=["asset_id", "period_start", "log", "n"])
        out = pd.DataFrame(
            {
                "asset_id": logs[cols["asset"]].astype(str),
                "period_start": logs[cols["ts"]].dt.floor(self.frequency),
                "log": logs[cols["log"]].astype(str),
            }
        )
        return (
            out.groupby(list(out.columns), as_index=False, sort=True)
            .size()
            .rename(columns={"size": "n"})
        )

    def _keep_log_map(self, new: pd.DataFrame, counts: pd.DataFrame) -> None:
        """Add this run's free-text log map to the kept one (newer labels win),
        keeping only logs the logs panel still has."""
        path = self.path / "history" / LOG_MAP
        merged = pd.concat(
            [_read_table(path) if path.is_file() else None, new], ignore_index=True
        )
        merged = merged.drop_duplicates("log", keep="last")
        merged = merged[merged["log"].isin(set(counts["log"].astype(str)))]
        _write_parquet(path, merged.reset_index(drop=True))

    def log_map(self) -> Optional[pd.DataFrame]:
        """Each kept log's system and subsystem (``log``, ``system``,
        ``subsystem``): the code map for a fixed-log model, or for a free-text
        model what scoring matched (empty labels when it matched none). None
        when neither is known."""
        code_map = _bundle_code_map(self.path / BUNDLE)
        if code_map is not None:
            return code_map
        path = self.path / "history" / LOG_MAP
        return _read_table(path) if path.is_file() else None

    def log_counts(self) -> pd.DataFrame:
        """How many logs of each kind each asset had in each scored period:
        ``asset_id``, ``period_start``, ``log``, ``n``. Kept for the last
        180 days of data. A monitor made before this was kept starts from the
        raw-log history it still has."""
        kept = self.path / "history" / LOG_COUNTS
        if kept.is_file():
            return _read_table(kept)
        return self._count_logs(self._history())

    def set_storage(self, kind: str) -> Dict[str, int]:
        """Move the scores, run records, alerts and state to another kind of
        storage: ``"files"`` or ``"sqlite"``. Everything is copied and
        checked before the old copy is removed. Returns what was moved.
        Stop the fleet app and any scheduled run first."""
        if kind not in storage.KINDS:
            raise MonitorError(f"storage must be one of: {', '.join(storage.KINDS)}.")
        if kind == self.store.kind:
            raise MonitorError(f"This monitor already uses {kind} storage.")
        lock = self._acquire_lock()
        try:
            new = storage.open_store(self.path, kind)
            new.clear()  # nothing half-moved from an earlier try
            try:
                moved = storage.copy_store(self.store, new)
            except BaseException:
                new.clear()
                raise
            self.config["storage"] = kind
            _write_json(self.path / CONFIG, self.config)
            old, self.store = self.store, new
            old.clear()
            return moved
        finally:
            lock.unlink(missing_ok=True)

    def status(self) -> Dict[str, Any]:
        scores, state, runs = self._scores(), self._state(), self.runs()
        last = runs[-1] if runs else None
        failed = [r for r in runs if r.get("status") == "failed"]
        last_ok = next((r for r in reversed(runs) if r.get("status") == "ok"), None)
        return {
            "folder": str(self.path),
            "storage": self.store.kind,
            "deployment_id": self.deployment["deployment_id"],
            "fleet_name": self.config["fleet_name"],
            "runs": len(runs),
            "runs_failed": len(failed),
            "last_run": last
            and {
                k: last.get(k)
                for k in (
                    "run_id",
                    "status",
                    "trigger",
                    "started_at",
                    "rows_new",
                    "periods_upserted",
                    "reason",
                )
                if last.get(k) is not None
            },
            "last_successful_run": last_ok and last_ok["run_id"],
            "model_warnings": self.model_warnings(),
            "latest_timestamp": state.get("latest_timestamp"),
            "assets": len(state.get("known_assets", {})),
            "periods_scored": len(scores),
            "provisional_periods": int(scores["provisional"].sum())
            if len(scores)
            else 0,
            "bands": self.config.get("bands"),
            "inbox_waiting": len(self.inbox_files()),
            "open_alerts": len(self.alerts("open")),
        }

    def spec(self) -> Dict[str, Any]:
        """What the dashboard shows: ``app.json`` if the folder has one,
        otherwise the standard layout."""
        from amygda_ops_risk_score.monitor import spec as app_spec

        path = self.path / app_spec.SPEC_FILE
        return app_spec.load_spec(path) if path.is_file() else app_spec.default_spec()

    def set_spec(self, spec: Union[Dict[str, Any], PathLike, None]) -> Path:
        """Save what the dashboard shows as ``app.json`` (a dict, a JSON file,
        or None for the standard layout). The spec is checked first. A logo
        it names is copied into the monitor folder, so the folder stays
        complete if the original moves. A spec that doesn't mention a
        schedule leaves the current one as it is."""
        from amygda_ops_risk_score.monitor import spec as app_spec

        base = Path.cwd()
        given = spec if isinstance(spec, dict) else {}
        if spec is not None and not isinstance(spec, dict):
            source = Path(spec).expanduser().resolve()
            base = source.parent
            spec = app_spec.load_spec(source)
            given = json.loads(source.read_text())
        spec = app_spec.validate_spec(spec)
        if "schedule" not in given:
            # A new layout doesn't cancel a schedule set in the app.
            try:
                spec["schedule"] = self.spec()["schedule"]
            except app_spec.SpecError:
                pass
        logo = spec["theme"]["logo"]
        if logo:
            src = Path(logo).expanduser()
            src = src if src.is_absolute() else base / src
            app_spec.read_logo(str(src))  # found, and not too large
            kept = self.path / f"logo{src.suffix.lower()}"
            if src.resolve() != kept.resolve():
                shutil.copyfile(src, kept)
            spec["theme"]["logo"] = kept.name
        return app_spec.save_spec(spec, self.path / app_spec.SPEC_FILE)

    def dashboard(
        self, output: Optional[PathLike] = None, failures=None, preview: bool = False
    ) -> Path:
        """Rebuild the dashboard from the saved scores. Returns its path.

        It is laid out from ``app.json`` when the folder has one. ``preview``
        shows placeholders for chosen panels that have no data yet."""
        from amygda_ops_risk_score.monitor.dashboard import build_dashboard

        spec = self.spec()
        scores = self._scores()
        if not len(scores):
            raise MonitorError(
                "No scores yet: add a file of logs and run. To see the layout "
                "before then, use `amygda-risk design --model <complete model zip>`."
            )
        weights, pairs = _bundle_weights(self.path / BUNDLE)
        wants_logs = any(
            p["type"] == "asset_logs" for t in spec["tabs"] for p in t["panels"]
        )
        return build_dashboard(
            scores,
            output or self.path / "dashboard" / "index.html",
            logs=self.log_counts() if wants_logs else None,
            code_map=self.log_map() if wants_logs else None,
            rolling_window=self.deployment.get("rolling_window"),
            fleet_name=self.config["fleet_name"],
            bands=self.config.get("bands")
            or _bands_from(scores["operational_risk"], basis=_SHOWN_BASIS),
            feature_frequency=self.deployment["feature_frequency"],
            weights=weights,
            system_pairs=pairs,
            runs=self.runs(),
            alerts=self.alerts(),
            failures=failures,
            model_checks=self.config.get("model_checks"),
            days=self.config.get("dashboard_days"),
            spec=spec,
            preview=preview,
            spec_dir=self.path,
            journey=("free-text" if self.deployment["is_free_text"] else "fixed-log"),
            weights_source=self.deployment.get("weights_source"),
        )

    def score_once(self, inputs, output_dir: Optional[PathLike] = None) -> Path:
        """Score a file without changing the monitor: no history is used or
        kept, and nothing is merged. Writes ``scores.parquet`` and a dashboard
        to ``output_dir`` (default: a new folder under ``oneoff/``)."""
        from amygda_ops_risk_score.monitor.dashboard import build_dashboard

        logs, counts, _ = self._load_logs(
            inputs if isinstance(inputs, list) else [inputs]
        )
        if not len(logs):
            raise MonitorError("No rows to score.")
        scores, _, _ = self._score(logs.sort_values(self.columns["ts"]), None)
        out = Path(output_dir) if output_dir else self.path / "oneoff" / _run_id()
        out.mkdir(parents=True, exist_ok=True)
        scores["provisional"] = False
        _write_parquet(out / "scores.parquet", scores)
        weights, pairs = _bundle_weights(self.path / BUNDLE)
        build_dashboard(
            scores,
            out / "index.html",
            fleet_name=self.config["fleet_name"],
            bands=self.config.get("bands")
            or _bands_from(scores["operational_risk"], basis=_SHOWN_BASIS),
            feature_frequency=self.deployment["feature_frequency"],
            weights=weights,
            system_pairs=pairs,
            journey=("free-text" if self.deployment["is_free_text"] else "fixed-log"),
            weights_source=self.deployment.get("weights_source"),
        )
        return out


# ---------------------------------------------------------------------------


def _check_bands(bands: Dict[str, Any]) -> None:
    try:
        w, h = float(bands["watch"]), float(bands["high"])
    except (KeyError, TypeError, ValueError):
        raise MonitorError('bands must look like {"watch": 35, "high": 40}.')
    if not 0 <= w < h <= 100:
        raise MonitorError("bands need 0 <= watch < high <= 100.")


_TRAINING_BASIS = (
    "From the model's training scores: watch is the 95th and high the 99th "
    "percentile."
)
_FIRST_RUN_BASIS = (
    "Provisional, from the first run: watch is the 95th and high the 99th "
    "percentile of its scores."
)

_SHOWN_BASIS = "From the scores shown: watch is the 95th and high the 99th percentile."


def _bands_from_training(model: PathLike) -> Optional[Dict[str, Any]]:
    """Bands from the training scores in a complete model zip, if it has them.

    Read here only; the training scores are never uploaded.
    """
    import io
    import zipfile

    try:
        with zipfile.ZipFile(model) as zf:
            data = zf.read("risk_score/training_scores.parquet")
        risk = pd.read_parquet(io.BytesIO(data), columns=["operational_risk"])
    except Exception:
        return None
    if not len(risk):
        return None
    return _bands_from(risk["operational_risk"], basis=_TRAINING_BASIS)


def _bands_from(risk: pd.Series, basis: str = _FIRST_RUN_BASIS) -> Dict[str, Any]:
    vals = pd.to_numeric(risk, errors="coerce").dropna()
    watch, high = (
        round(float(vals.quantile(0.95)), 1),
        round(float(vals.quantile(0.99)), 1),
    )
    if high <= watch:
        high = round(watch + 1, 1)
    if high <= 0:
        return {
            "watch": 35.0,
            "high": 40.0,
            "basis": "Default levels: the scores so far are all near 0.",
        }
    return {"watch": watch, "high": high, "basis": basis}


def _bundle_weights(bundle: Path) -> tuple:
    """Weights and hierarchy rows from the saved bundle, if any."""
    if not bundle.is_file():
        return None, None
    import zipfile

    with zipfile.ZipFile(bundle) as zf:
        weights = json.loads(zf.read("weights.json"))
        hierarchy = json.loads(zf.read("hierarchy.json"))
    return weights, hierarchy


def _bundle_code_map(bundle: Path) -> Optional[pd.DataFrame]:
    """A fixed-log model's log codes with their system and subsystem
    (``log``, ``system``, ``subsystem``), from the saved bundle."""
    import io
    import zipfile

    if not bundle.is_file():
        return None
    with zipfile.ZipFile(bundle) as zf:
        if "code_map.parquet" not in zf.namelist():
            return None
        table = pd.read_parquet(io.BytesIO(zf.read("code_map.parquet")))
    return _code_map(table)


def _code_map(table: pd.DataFrame) -> Optional[pd.DataFrame]:
    if not {"system_name", "subsystem_name"} <= set(table.columns):
        return None
    log = [c for c in table.columns if not c.startswith(("system", "subsystem"))]
    if not log:
        return None
    return pd.DataFrame(
        {
            "log": table[log[0]].astype(str),
            "system": table["system_name"].astype(str),
            "subsystem": table["subsystem_name"].astype(str),
        }
    ).drop_duplicates("log")


def preview_from_model(
    model: PathLike,
    output: PathLike,
    spec: Union[Dict[str, Any], PathLike, None] = None,
    *,
    fleet_name: str = "Fleet",
    bands: Optional[Dict[str, Any]] = None,
    monitor: Optional["Monitor"] = None,
) -> Path:
    """Show a layout before there is anything to score: build the page from
    the scores saved in a complete model zip. Returns the page's path.

    Nothing is deployed, sent or saved besides the page. Panels that need a
    run (what changed, alerts, run history) show as placeholders.

    Args:
        model: ``complete_model_<id>.zip``.
        output: Where to write the ``.html`` page.
        spec: The app spec, as a dict or a JSON file. Default: the monitor's
            layout, or the standard one.
        fleet_name: Used for the title when the spec has none.
        bands: ``{"watch": .., "high": ..}``. Default: the monitor's, or the
            95th and 99th percentile of the model's training scores.
        monitor: A monitor to take the layout, name and bands from.
    """
    import io
    import zipfile

    from amygda_ops_risk_score.deployment import unmapped_codes
    from amygda_ops_risk_score.monitor import spec as app_spec
    from amygda_ops_risk_score.monitor.dashboard import build_dashboard

    model = Path(model).expanduser()
    try:
        zf = zipfile.ZipFile(model)
    except (OSError, zipfile.BadZipFile):
        raise MonitorError(f"{model} is not a model zip that can be read.") from None
    with zf:
        names = set(zf.namelist())
        need = (
            "risk_score/risk_scores.parquet",
            "risk_score/risk_score_config.json",
            "outputs/model_config.json",
            "labels/accepted_hierarchy.json",
        )
        missing = [n for n in need if n not in names]
        if missing:
            raise MonitorError(
                f"{model.name} has no {missing[0]}, so there are no scores to "
                "preview with. Use the complete_model zip saved after the risk "
                "scores were generated."
            )
        scores = pd.read_parquet(io.BytesIO(zf.read(need[0])))
        risk_config = json.loads(zf.read(need[1]))
        model_config = json.loads(zf.read(need[2]))
        pairs = json.loads(zf.read(need[3]))
        source = risk_config.get("weights_source", "labelling")
        w = model_config
        if source == "supervised" and "risk_score/trained_weights.json" in names:
            w = json.loads(zf.read("risk_score/trained_weights.json"))
    weights = {
        "system_weights": w.get("system_weights", {}),
        "subsystem_weights": w.get("subsystem_weights", {}),
    }

    spec_dir: Optional[Path] = None
    if spec is not None and not isinstance(spec, dict):
        source_file = Path(spec).expanduser().resolve()
        spec_dir = source_file.parent
        spec = app_spec.load_spec(source_file)
    if monitor is not None:
        fleet_name = monitor.config["fleet_name"]
        bands = bands or monitor.config.get("bands")
        if spec is None:
            spec, spec_dir = monitor.spec(), monitor.path
    bands = (
        bands
        or _bands_from_training(model)
        or _bands_from(scores["operational_risk"], basis=_SHOWN_BASIS)
    )
    _check_bands(bands)
    # The logs the model's own scores were made from, for the logs panel.
    logs = code_map = None
    try:
        freq = pd.Timedelta(risk_config.get("feature_frequency", "1D"))
        with zipfile.ZipFile(model) as zf:
            raw = pd.read_parquet(
                io.BytesIO(zf.read("risk_score/generation_input.parquet"))
            )
            # Each log's system and subsystem: the code map for a fixed-log
            # model, what generation matched for a free-text one.
            labelled = (
                "risk_score/classified_logs.parquet"
                if model_config.get("is_free_text", True)
                else "labels/deduplicated_predictions.parquet"
            )
            if labelled in zf.namelist():
                preds = pd.read_parquet(io.BytesIO(zf.read(labelled)))
                keep = [model_config["log_column"], "system_name", "subsystem_name"]
                code_map = _code_map(preds[keep].fillna(""))
        if "timestamp" in raw and pd.api.types.is_datetime64_any_dtype(
            raw["timestamp"]
        ):
            when = raw["timestamp"]  # as the API read it, with the time of day
        else:
            when = _parse_timestamps(
                raw[risk_config["timestamp_mapping"]],
                risk_config.get("date_format", "infer"),
            )
        logs = pd.DataFrame(
            {
                "asset_id": raw[risk_config["asset_id_mapping"]].astype(str),
                "period_start": when.dt.floor(freq),
                "log": raw[model_config["log_column"]].astype(str),
            }
        ).dropna()
        logs = logs.groupby(list(logs.columns), as_index=False).size()
        logs = logs.rename(columns={"size": "n"})
    except Exception:  # noqa: BLE001 - the preview does not depend on it
        logs = None
    checks: Dict[str, Any] = {}
    try:
        unmapped = unmapped_codes(str(model))
        if unmapped is not None:
            checks["unmapped_codes"] = unmapped
    except Exception:  # noqa: BLE001 - the preview does not depend on it
        pass
    return build_dashboard(
        scores,
        output,
        fleet_name=fleet_name,
        bands=dict(bands, basis=bands.get("basis", "Set for this preview.")),
        feature_frequency=risk_config.get("feature_frequency", "1D"),
        weights=weights,
        system_pairs=pairs,
        model_checks=checks,
        logs=logs,
        code_map=code_map,
        rolling_window=risk_config.get("rolling_window"),
        spec=spec,
        preview=True,
        spec_dir=spec_dir,
        journey="free-text" if model_config.get("is_free_text", True) else "fixed-log",
        weights_source=source,
    )
