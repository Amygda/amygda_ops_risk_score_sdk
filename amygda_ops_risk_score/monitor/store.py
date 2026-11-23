"""Where a monitor keeps its scores, run records, alerts and state.

Two kinds, chosen when the monitor is created (``"storage"`` in
``monitor.json``) and changed later with ``Monitor.set_storage``:

``files`` (the default)
    ``scores/scores.parquet``, ``runs/<run_id>/run.json``,
    ``alerts/alerts.json``, ``state.json`` and ``app_state.json``.

``sqlite``
    One database file, ``monitor.db``, with tables ``scores`` (one row per
    asset and period, one column per score), ``runs``, ``alerts`` and
    ``meta``. Any SQLite tool can read it.

The raw-log history, the scoring bundle, the inbox, ``app.json`` and the
dashboard are files either way.
"""

from __future__ import annotations

from contextlib import closing
from datetime import date
import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, List

import pandas as pd

KINDS = ("files", "sqlite")
DB_FILE = "monitor.db"
SCORES_FILE = "scores/scores.parquet"
ALERTS_FILE = "alerts/alerts.json"
STATE_FILE = "state.json"
APP_STATE_FILE = "app_state.json"


class StoreError(Exception):
    """The storage is not one this version can use."""


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def _dumps(obj: Any) -> str:
    return json.dumps(obj, indent=1, default=str)


def _mtime(path: Path) -> str:
    return str(path.stat().st_mtime_ns) if path.exists() else "-"


class FileStore:
    """Parquet and JSON files in the monitor folder."""

    kind = "files"

    def __init__(self, folder: Path):
        self.folder = Path(folder)

    def prepare(self) -> None:
        for sub in ("scores", "runs"):
            (self.folder / sub).mkdir(parents=True, exist_ok=True)

    def check(self) -> None:
        pass

    # scores
    def has_scores(self) -> bool:
        return (self.folder / SCORES_FILE).exists()

    def scores(self) -> pd.DataFrame:
        p = self.folder / SCORES_FILE
        return pd.read_parquet(p) if p.exists() else pd.DataFrame()

    def save_scores(self, df: pd.DataFrame) -> None:
        p = self.folder / SCORES_FILE
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp.parquet")
        df.to_parquet(tmp, index=False)
        tmp.replace(p)

    # run records
    def runs(self) -> List[Dict[str, Any]]:
        folder = self.folder / "runs"
        out = []
        for d in sorted(folder.iterdir()) if folder.is_dir() else []:
            f = d / "run.json"
            if f.is_file():
                out.append(json.loads(f.read_text()))
        return out

    def last_run(self) -> Dict[str, Any] | None:
        folder = self.folder / "runs"
        for d in sorted(folder.iterdir(), reverse=True) if folder.is_dir() else []:
            f = d / "run.json"
            if f.is_file():
                return json.loads(f.read_text())
        return None

    def save_run(self, run_id: str, record: Dict[str, Any]) -> None:
        _write_text(self.folder / "runs" / run_id / "run.json", _dumps(record))

    # alerts
    def alerts(self) -> List[Dict[str, Any]]:
        try:
            return json.loads((self.folder / ALERTS_FILE).read_text())
        except (OSError, ValueError):
            return []

    def save_alerts(self, alerts: List[Dict[str, Any]]) -> None:
        _write_text(self.folder / ALERTS_FILE, _dumps(alerts))

    # state
    def _file(self, name: str) -> Path:
        return self.folder / (APP_STATE_FILE if name == "app" else STATE_FILE)

    def state(self, name: str = "monitor") -> Dict[str, Any]:
        """``"monitor"``: what the runs have seen. ``"app"``: the fleet app's."""
        try:
            return json.loads(self._file(name).read_text())
        except (OSError, ValueError):
            return {}

    def save_state(self, state: Dict[str, Any], name: str = "monitor") -> None:
        _write_text(self._file(name), _dumps(state))

    def version(self) -> str:
        """Changes whenever scores, run records or alerts do."""
        return ".".join(
            _mtime(self.folder / rel) for rel in (SCORES_FILE, "runs", ALERTS_FILE)
        )

    def clear(self) -> None:
        """Remove what this store wrote (after moving it to another kind)."""
        runs = self.folder / "runs"
        for d in list(runs.iterdir()) if runs.is_dir() else []:
            (d / "run.json").unlink(missing_ok=True)
        files = (SCORES_FILE, ALERTS_FILE, STATE_FILE, APP_STATE_FILE)
        for rel in files:
            (self.folder / rel).unlink(missing_ok=True)
        folders = list(runs.iterdir()) if runs.is_dir() else []
        for d in folders + [runs, self.folder / "scores", self.folder / "alerts"]:
            try:
                d.rmdir()  # only when empty
            except OSError:
                pass


_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY, status TEXT, trigger TEXT, started_at TEXT,
    finished_at TEXT, record TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS alerts (
    number INTEGER PRIMARY KEY, id TEXT, rule TEXT, asset_id TEXT,
    severity TEXT, status TEXT, message TEXT, raised_at TEXT, closed_at TEXT,
    record TEXT NOT NULL);
"""
_SCHEMA_VERSION = 1


def _q(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _column_kind(series: pd.Series) -> str:
    """How a column is kept in SQLite, so it reads back as it was written."""
    if pd.api.types.is_bool_dtype(series):
        return "bool"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    if pd.api.types.is_integer_dtype(series):
        return "int"
    if pd.api.types.is_float_dtype(series):
        return "float"
    first = series.dropna()
    if len(first) and isinstance(first.iloc[0], date):
        return "date"
    return "text"


_SQL_TYPE = {"bool": "INTEGER", "int": "INTEGER", "float": "REAL"}


class SqliteStore:
    """One SQLite file, ``monitor.db``, in the monitor folder."""

    kind = "sqlite"

    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.path = self.folder / DB_FILE

    def _connect(self) -> sqlite3.Connection:
        # A connection per call: the app reads from several threads.
        return sqlite3.connect(self.path, timeout=30)

    def prepare(self) -> None:
        with closing(self._connect()) as con, con:
            con.executescript(_SCHEMA)
            con.execute(
                "INSERT OR IGNORE INTO meta VALUES ('schema_version', ?)",
                (json.dumps(_SCHEMA_VERSION),),
            )
        self.check()

    def check(self) -> None:
        if not self.path.is_file():
            raise StoreError(
                f"This monitor keeps its data in {DB_FILE}, which is missing "
                f"from {self.folder}."
            )
        if self._meta("schema_version") != _SCHEMA_VERSION:
            raise StoreError(
                f"{DB_FILE} was written by a newer version of the SDK. "
                "Upgrade amygda-ops-risk-score to open this monitor."
            )

    def _meta(self, key: str, default: Any = None) -> Any:
        if not self.path.exists():
            return default
        with closing(self._connect()) as con:
            row = con.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def _set_meta(self, con: sqlite3.Connection, key: str, value: Any) -> None:
        con.execute(
            "INSERT INTO meta VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value, default=str)),
        )

    def _changed(self, con: sqlite3.Connection) -> None:
        """Count a change the page would show (see ``version``)."""
        con.execute(
            "INSERT INTO meta VALUES ('revision', '1') ON CONFLICT(key) "
            "DO UPDATE SET value = CAST(value AS INTEGER) + 1"
        )

    # scores
    def has_scores(self) -> bool:
        return bool(self._meta("scores_columns"))

    def scores(self) -> pd.DataFrame:
        kinds = self._meta("scores_columns")
        if not kinds:
            return pd.DataFrame()
        cols = [name for name, _ in kinds]
        with closing(self._connect()) as con:
            rows = con.execute(
                f"SELECT {', '.join(_q(c) for c in cols)} FROM scores ORDER BY rowid"
            ).fetchall()
        df = pd.DataFrame(rows, columns=cols)
        for name, kind in kinds:
            if kind == "datetime":
                df[name] = pd.to_datetime(df[name], format="ISO8601")
            elif kind == "date":
                df[name] = pd.to_datetime(df[name], format="ISO8601").dt.date
            elif kind == "bool":
                df[name] = df[name].astype(bool)
            elif kind == "float":
                df[name] = df[name].astype("float64")
            elif kind == "int":
                df[name] = df[name].astype("int64")
        return df

    def save_scores(self, df: pd.DataFrame) -> None:
        kinds = [(str(c), _column_kind(df[c])) for c in df.columns]
        cells = []
        for (name, kind), col in zip(kinds, df.columns):
            s = df[col]
            if kind == "datetime":
                s = s.dt.strftime("%Y-%m-%d %H:%M:%S.%f").str.replace(
                    r"\.000000$", "", regex=True
                )
            elif kind == "date":
                s = s.map(lambda v: v.isoformat() if isinstance(v, date) else v)
            elif kind == "bool":
                s = s.astype(int)
            cells.append(s.astype(object).where(s.notna(), None).tolist())
        defs = ", ".join(f"{_q(n)} {_SQL_TYPE.get(k, 'TEXT')}" for n, k in kinds)
        marks = ", ".join("?" for _ in kinds)
        keys = [n for n, _ in kinds if n in ("asset_id", "period_start")]
        with closing(self._connect()) as con, con:
            con.execute("DROP TABLE IF EXISTS scores")
            con.execute(f"CREATE TABLE scores ({defs})")
            con.executemany(
                f"INSERT INTO scores VALUES ({marks})",
                zip(*cells),
            )
            if len(keys) == 2:
                con.execute(
                    "CREATE INDEX scores_asset_period ON scores "
                    "(asset_id, period_start)"
                )
            self._set_meta(con, "scores_columns", kinds)
            self._changed(con)

    # run records
    def runs(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        with closing(self._connect()) as con:
            rows = con.execute("SELECT record FROM runs ORDER BY run_id").fetchall()
        return [json.loads(r[0]) for r in rows]

    def last_run(self) -> Dict[str, Any] | None:
        if not self.path.exists():
            return None
        with closing(self._connect()) as con:
            row = con.execute(
                "SELECT record FROM runs ORDER BY run_id DESC LIMIT 1"
            ).fetchone()
        return json.loads(row[0]) if row else None

    def save_run(self, run_id: str, record: Dict[str, Any]) -> None:
        with closing(self._connect()) as con, con:
            con.execute(
                "INSERT OR REPLACE INTO runs VALUES (?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    record.get("status"),
                    record.get("trigger"),
                    record.get("started_at"),
                    record.get("finished_at"),
                    json.dumps(record, default=str),
                ),
            )
            self._changed(con)

    # alerts
    def alerts(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        with closing(self._connect()) as con:
            rows = con.execute("SELECT record FROM alerts ORDER BY number").fetchall()
        return [json.loads(r[0]) for r in rows]

    def save_alerts(self, alerts: List[Dict[str, Any]]) -> None:
        rows = [
            (
                a["number"],
                a.get("id"),
                a.get("rule"),
                a.get("asset_id"),
                a.get("severity"),
                a.get("status"),
                a.get("message"),
                a.get("raised_at"),
                a.get("closed_at"),
                json.dumps(a, default=str),
            )
            for a in alerts
        ]
        with closing(self._connect()) as con, con:
            con.execute("DELETE FROM alerts")
            con.executemany("INSERT INTO alerts VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
            self._changed(con)

    # state
    def state(self, name: str = "monitor") -> Dict[str, Any]:
        return self._meta(f"state:{name}", {})

    def save_state(self, state: Dict[str, Any], name: str = "monitor") -> None:
        with closing(self._connect()) as con, con:
            self._set_meta(con, f"state:{name}", state)

    def version(self) -> str:
        """Changes whenever scores, run records or alerts do."""
        return str(self._meta("revision", 0))

    def clear(self) -> None:
        for suffix in ("", "-journal", "-wal", "-shm"):
            Path(str(self.path) + suffix).unlink(missing_ok=True)


def open_store(folder: Path, kind: str = "files"):
    """The store of a monitor folder."""
    if kind not in KINDS:
        raise StoreError(
            f'Unknown storage "{kind}". Choose from: {", ".join(KINDS)}. '
            "(A newer version of the SDK may be needed for this monitor.)"
        )
    return SqliteStore(folder) if kind == "sqlite" else FileStore(folder)


def copy_store(src, dst) -> Dict[str, int]:
    """Copy everything from one store to another. Returns what was copied."""
    dst.prepare()
    scores = src.scores()
    if len(scores.columns):
        dst.save_scores(scores)
    runs = src.runs()
    for r in runs:
        dst.save_run(r["run_id"], r)
    alerts = src.alerts()
    if alerts:
        dst.save_alerts(alerts)
    for name in ("monitor", "app"):
        state = src.state(name)
        if state:
            dst.save_state(state, name)
    counts = {"scores": len(scores), "runs": len(runs), "alerts": len(alerts)}
    found = {
        "scores": len(dst.scores()),
        "runs": len(dst.runs()),
        "alerts": len(dst.alerts()),
    }
    if found != counts:
        raise StoreError(f"The copy is incomplete ({found} of {counts}).")
    return counts
