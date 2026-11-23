"""Dashboard as code: one self-contained HTML page built from risk scores.

The page is laid out from an app spec (``monitor.spec``): which tabs, which
panels on each and which header tiles. The default has tabs for the
fleet (heatmap and ranking), asset detail (trend, systems, drivers) and the
model (bands, weights, unused log codes, known gaps). With monitor runs it adds
"Since the last run" to the fleet tab, a Runs tab (every run, its trigger,
status and warnings), a banner when the last run failed, and hatches
provisional periods.

All values come from the scores the API returned; the page only summarises
them. Data is embedded as CSV blocks; charts use d3 7.9.0 from cdnjs.
"""

from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

import pandas as pd

from amygda_ops_risk_score.monitor.alerts import describe_rule
from amygda_ops_risk_score.monitor.alerts import settings as alert_settings
from amygda_ops_risk_score.monitor.spec import menu
from amygda_ops_risk_score.monitor.spec import PANELS
from amygda_ops_risk_score.monitor.spec import RANK_BY
from amygda_ops_risk_score.monitor.spec import TILES
from amygda_ops_risk_score.monitor.spec import read_logo
from amygda_ops_risk_score.monitor.spec import validate_spec

MAX_BYTES = 10 * 1024 * 1024
# The logs panel: the newest logs are kept up to these limits, so a large
# fleet or long free-text logs can't make the page unusable.
MAX_LOG_ROWS = 100_000
MAX_LOG_CHARS = 2_500_000
MAX_LOG_TEXT = 300


def _template() -> str:
    return (
        resources.files("amygda_ops_risk_score.monitor")
        .joinpath("template.html")
        .read_text()
    )


def _csv(df: pd.DataFrame) -> str:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    # A "</" inside a script block would end it early.
    return buf.getvalue().replace("</", "<\\/")


def _block(name: str, content: str, kind: str = "text/csv") -> str:
    return f'<script type="{kind}" id="{name}">\n{content}</script>\n'


def _made_on() -> str:
    now = datetime.now(timezone.utc)  # %-d isn't portable to Windows
    return f"{now:%b} {now.day}, {now:%Y %H:%M} UTC"


def _freq_label(td: pd.Timedelta) -> str:
    s = int(td.total_seconds())
    if s % 86400 == 0:
        d = s // 86400
        return "day" if d == 1 else f"{d} days"
    if s % 3600 == 0:
        h = s // 3600
        return "hour" if h == 1 else f"{h} hours"
    return f"{s // 60} minutes"


def _log_block(
    logs: Optional[pd.DataFrame],
    code_map: Optional[pd.DataFrame],
    shown: pd.DataFrame,
    freq: pd.Timedelta,
    tfmt: str,
) -> Dict[str, Any]:
    """The logs panel's data, as small as it can be made: each log's text is
    written once, and each row is ``[asset, time, log, count]`` by position.
    Only the assets and dates on the page are kept, newest first up to the
    limits."""
    empty: Dict[str, Any] = {"logs": [], "assets": [], "rows": [], "mapped": False}
    if logs is None or not len(logs):
        return empty
    lg = logs.copy()
    lg["period_start"] = pd.to_datetime(lg["period_start"])
    lg["asset_id"] = lg["asset_id"].astype(str)
    lg = lg[
        lg["asset_id"].isin(set(shown["asset_id"]))
        & (lg["period_start"] >= shown["period_start"].min().floor(freq))
    ]
    if not len(lg):
        return empty
    lg["log"] = lg["log"].astype(str).str.slice(0, MAX_LOG_TEXT)
    lg = lg.groupby(["asset_id", "period_start", "log"], as_index=False)["n"].sum()
    lg = lg.sort_values("period_start", ascending=False).reset_index(drop=True)
    cut = len(lg)
    if cut > MAX_LOG_ROWS:
        cut = MAX_LOG_ROWS
    first_seen = ~lg["log"].duplicated()
    chars = (lg["log"].str.len() * first_seen).cumsum()
    over = chars > MAX_LOG_CHARS
    if over.any():
        cut = min(cut, int(over.idxmax()))
    truncated = cut < len(lg)
    lg = lg.iloc[:cut].sort_values(["asset_id", "period_start"])
    texts = list(dict.fromkeys(lg["log"]))
    where = {}
    if code_map is not None and len(code_map):
        where = {
            str(r.log): [str(r.system), str(r.subsystem)]
            for r in code_map.itertuples(index=False)
        }
    assets = sorted(lg["asset_id"].unique())
    a_idx = {a: i for i, a in enumerate(assets)}
    l_idx = {t: i for i, t in enumerate(texts)}
    times = lg["period_start"].dt.strftime(tfmt)
    return {
        "logs": [[t] + where.get(t, []) for t in texts],
        "assets": assets,
        "rows": [
            [a_idx[a], t, l_idx[g], int(n)]
            for a, t, g, n in zip(lg["asset_id"], times, lg["log"], lg["n"])
        ],
        "mapped": bool(where),
        "from": lg["period_start"].min().strftime(tfmt) if truncated else None,
    }


def _systems(
    scores: pd.DataFrame, hierarchy: Optional[Sequence[Dict[str, str]]]
) -> tuple:
    """Ordered systems and (system, subsystem, column) triples."""
    if hierarchy:
        subs, systems = [], []
        for r in hierarchy:
            pair = r["system_subsystem_pair"]
            sys_ = r.get("system") or pair.split("-", 1)[0]
            sub = r.get("subsystem") or pair.split("-", 1)[-1]
            col = f"{pair}_calibrated_risk"
            if col in scores.columns:
                subs.append((sys_, sub, col))
            if sys_ not in systems and f"{sys_}_system_risk" in scores.columns:
                systems.append(sys_)
        return systems, subs
    systems = [
        c[: -len("_system_risk")] for c in scores.columns if c.endswith("_system_risk")
    ]
    subs = []
    for c in scores.columns:
        if c.endswith("_calibrated_risk") and "-" in c:
            sys_, sub = c[: -len("_calibrated_risk")].split("-", 1)
            if sys_ and sub:
                subs.append((sys_, sub, c))
    return systems, subs


def build_dashboard(
    scores: pd.DataFrame,
    output_path: Union[str, Path],
    *,
    fleet_name: str,
    bands: Dict[str, Any],
    feature_frequency: str = "1D",
    weights: Optional[Dict[str, Any]] = None,
    system_pairs: Optional[Sequence[Dict[str, str]]] = None,
    runs: Optional[List[Dict[str, Any]]] = None,
    alerts: Optional[List[Dict[str, Any]]] = None,
    failures: Optional[pd.DataFrame] = None,
    days: Optional[int] = None,
    journey: str = "fixed-log",
    weights_source: Optional[str] = None,
    known_gaps: Optional[List[str]] = None,
    model_checks: Optional[Dict[str, Any]] = None,
    spec: Optional[Dict[str, Any]] = None,
    preview: bool = False,
    spec_dir: Union[str, Path, None] = None,
    logs: Optional[pd.DataFrame] = None,
    code_map: Optional[pd.DataFrame] = None,
    rolling_window: Optional[str] = None,
) -> Path:
    """Write the dashboard HTML. Returns its path.

    Args:
        scores: Risk scores from ``client.score`` or a monitor: ``asset_id``,
            ``period_start``, ``operational_risk``, ``<system>_system_risk``,
            ``<system>-<subsystem>_calibrated_risk``; optional ``provisional``.
        output_path: Where to write the ``.html`` file.
        fleet_name: e.g. "Conveyor fleet".
        bands: ``{"watch": 35, "high": 40, "basis": "how they were chosen"}``.
        feature_frequency: The model's scoring frequency, e.g. "1D" or "1h".
        weights: ``{"system_weights": ..., "subsystem_weights": ...}`` used to
            score (from the bundle), for the "what the score is made of" chart.
        system_pairs: Hierarchy rows (``system``, ``subsystem``,
            ``system_subsystem_pair``) to order systems and subsystems.
        runs: Monitor run records; adds "Since the last run" and run health.
        alerts: The monitor's alerts (``Monitor.alerts()``), for the Alerts
            panel and tile.
        failures: Optional ``asset_id, failure_date`` to mark failures.
        days: Only show the most recent N days.
        known_gaps: Extra sentences for the "Known gaps" list.
        model_checks: From the monitor (``monitor.json``): e.g. the log codes
            the model maps to no subsystem, listed on the Model tab.
        spec: The app spec: which tabs, panels and header tiles to show (see
            ``monitor.spec``). Default: Fleet, Asset detail, Model and Runs.
        preview: Show a placeholder for a chosen panel that has no data yet
            (a Runs panel before the first run), so the whole layout can be
            reviewed. Otherwise such panels are left out.
        spec_dir: Folder a relative ``theme.logo`` path in the spec is looked
            up from (default: the current folder).
        logs: For the "Logs behind the score" panel: how many logs of each
            kind each asset had in each scored period (``asset_id``,
            ``period_start``, ``log``, ``n``; ``Monitor.log_counts()``). The
            log text is written into the page.
        code_map: A fixed-log model's codes with their ``system`` and
            ``subsystem`` (column ``log``), to say what each log counts
            toward.
        rolling_window: The model's rolling window, e.g. "7D": the logs
            behind one score are those of this long before it.
    """
    spec = validate_spec(spec)
    logo = spec["theme"]["logo"]
    logo_uri = read_logo(logo, spec_dir) if logo else None
    # A title the user chose is shown as they wrote it.
    title = spec["title"] or f"{fleet_name} risk"
    days = spec["days"] or days
    if scores is None or not len(scores):
        raise ValueError("No scores to show.")
    df = scores.copy()
    df["period_start"] = pd.to_datetime(df["period_start"])
    if days:
        cutoff = df["period_start"].max().normalize() - pd.Timedelta(days=days - 1)
        df = df[df["period_start"] >= cutoff]
    df = df.sort_values(["asset_id", "period_start"]).reset_index(drop=True)
    freq = pd.Timedelta(feature_frequency)
    daily = freq >= pd.Timedelta("1D")
    tfmt = "%Y-%m-%d" if daily else "%Y-%m-%dT%H:%M"
    df["t"] = df["period_start"].dt.strftime(tfmt)
    df["asset_id"] = df["asset_id"].astype(str)
    if "provisional" not in df.columns:
        df["provisional"] = False

    systems, subs = _systems(df, system_pairs)
    main = pd.DataFrame(
        {
            "asset_id": df["asset_id"],
            "t": df["t"],
            "risk": df["operational_risk"].astype(float).round(1),
            "provisional": df["provisional"].astype(bool).astype(int),
        }
    )
    for s in systems:
        main[s] = df[f"{s}_system_risk"].astype(float).round(1)

    long = []
    for sys_, sub, col in subs:
        v = df[col].astype(float).round(1)
        keep = v > 0
        if keep.any():
            long.append(
                pd.DataFrame(
                    {
                        "asset_id": df.loc[keep, "asset_id"],
                        "t": df.loc[keep, "t"],
                        "system": sys_,
                        "subsystem": sub,
                        "risk": v[keep],
                    }
                )
            )
    subsys = (
        pd.concat(long, ignore_index=True)
        if long
        else pd.DataFrame(columns=["asset_id", "t", "system", "subsystem", "risk"])
    )

    band_rows = pd.DataFrame(
        [
            {
                "band": "watch",
                "cutoff": float(bands["watch"]),
                "basis": bands.get("basis", ""),
            },
            {
                "band": "high",
                "cutoff": float(bands["high"]),
                "basis": bands.get("basis", ""),
            },
        ]
    )

    weight_rows = pd.DataFrame(columns=["system", "subsystem", "share"])
    if weights:
        sw, ssw = (
            weights.get("system_weights", {}),
            weights.get("subsystem_weights", {}),
        )
        rows = [
            {
                "system": s,
                "subsystem": sub,
                "share": round(
                    float(sw.get(s, 0)) * float(ssw.get(s, {}).get(sub, 0)), 4
                ),
            }
            for s, sub, _ in subs
        ]
        weight_rows = pd.DataFrame(rows, columns=["system", "subsystem", "share"])

    fail_rows = pd.DataFrame(columns=["asset_id", "failure_date"])
    if failures is not None and len(failures):
        f = failures.rename(
            columns={
                failures.columns[0]: "asset_id",
                failures.columns[1]: "failure_date",
            }
        )
        f = f.dropna(subset=["asset_id", "failure_date"])
        fail_rows = pd.DataFrame(
            {
                "asset_id": f["asset_id"].astype(str),
                "failure_date": pd.to_datetime(
                    f["failure_date"], errors="coerce"
                ).dt.strftime("%Y-%m-%d"),
            }
        ).dropna()

    run_rows = pd.DataFrame()
    change_rows = pd.DataFrame()
    if runs:
        run_rows = pd.DataFrame(
            [
                {
                    "run_id": r.get("run_id"),
                    "started_at": r.get("started_at"),
                    "finished_at": r.get("finished_at"),
                    "status": r.get("status"),
                    "trigger": r.get("trigger") or "",
                    "reason": r.get("reason") or "",
                    "data_from": (r.get("new_period") or {}).get("start") or "",
                    "data_to": (r.get("new_period") or {}).get("end") or "",
                    "rows_new": r.get("rows_new", 0),
                    "rows_already_seen": r.get("rows_already_seen", 0),
                    "rows_skipped": (r.get("rows_too_old") or 0)
                    + (r.get("rows_unreadable") or 0),
                    "periods": r.get("periods_upserted", 0),
                    "assets": r.get("assets_in_batch", 0),
                    "new_assets": len(r.get("new_assets") or []),
                    "unmatched_share": r.get("unmatched_share"),
                    "unmatched_basis": r.get("unmatched_basis") or "window",
                    "n_warnings": len(r.get("warnings") or []),
                    "warnings": " || ".join(r.get("warnings") or []),
                }
                for r in runs
            ]
        )
        last_ok = next((r for r in reversed(runs) if r.get("status") == "ok"), None)
        if last_ok and last_ok.get("changes"):
            ch = pd.DataFrame(last_ok["changes"])
            ch["highest_this_run_at"] = pd.to_datetime(
                ch["highest_this_run_at"]
            ).dt.strftime(tfmt)
            for col in ("first_period", "last_period"):
                # Runs recorded before these were kept show a count instead.
                ch[col] = pd.to_datetime(ch[col]).dt.strftime(tfmt) if col in ch else ""
            change_rows = ch[
                [
                    "asset_id",
                    "score_before_run",
                    "score_now",
                    "change",
                    "highest_this_run",
                    "highest_this_run_at",
                    "band_before_run",
                    "band_of_highest",
                    "periods_scored",
                    "first_period",
                    "last_period",
                ]
            ].round(1)

    gaps = list(known_gaps or [])
    gaps.append(
        "Scores exist only for periods with logs. A blank cell or a break in a line "
        "means no logs, not low risk."
    )
    if df["provisional"].any():
        gaps.append(
            "The newest period is provisional: its score can change when the rest "
            "of its data arrives in the next run."
        )
    if runs:
        last = next((r for r in reversed(runs) if r.get("status") == "ok"), None)
        if last and last.get("unmatched_share") is not None:
            what = (
                "of the new logs"
                if last.get("unmatched_basis") == "new"
                else "of the logs scored (history included)"
            )
            gaps.append(
                f"{last['unmatched_share']:.0%} {what} in the last run matched no "
                "subsystem and don't count toward the score."
            )
    unmapped = (model_checks or {}).get("unmapped_codes")
    if unmapped and unmapped.get("unmapped_share"):
        gaps.append(
            f"{unmapped['unmapped_share']:.0%} of the training logs have codes the "
            "model maps to no subsystem (listed above), so they never affect a score."
        )
    if weights:
        zero = [
            s for s, w in weights.get("system_weights", {}).items() if float(w) == 0
        ]
        if zero:
            gaps.append(
                "The model gives no weight to "
                f"{', '.join(z.replace('_', ' ') for z in zero)}, "
                "so activity there doesn't change the overall score."
            )
    if not len(fail_rows):
        gaps.append(
            "No failure records are shown, so alerts can't be checked against "
            "failures here."
        )

    wants_logs = any(
        p["type"] == "asset_logs" for t in spec["tabs"] for p in t["panels"]
    )
    log_data = _log_block(logs if wants_logs else None, code_map, df, freq, tfmt)
    window = pd.Timedelta(rolling_window) if rolling_window else None

    meta = {
        "fleet_name": fleet_name,
        "title": title,
        "systems": systems,
        "subsystems": [[s, sub] for s, sub, _ in subs],
        "frequency_seconds": int(freq.total_seconds()),
        "frequency_label": _freq_label(freq),
        "window_seconds": int(window.total_seconds()) if window is not None else None,
        "window_label": _freq_label(window) if window is not None else None,
        "journey": journey,
        "weights_source": weights_source or "labelling",
        "made_on": _made_on(),
        "known_gaps": gaps,
        "model_checks": model_checks or {},
        "spec": spec,
        "preview": bool(preview),
        "alert_rules": [describe_rule(r) for r in spec["alerts"]["rules"]],
        "alert_settings": alert_settings(spec["alerts"]["rules"]),
        "menu": menu(),
        "tiles": dict(TILES),
        "logo": logo_uri,
        "rank_label": RANK_BY[spec["rank_by"]],
        "panels": {
            name: {"title": p["title"], "shows": p["shows"], "needs": p.get("needs")}
            for name, p in PANELS.items()
        },
    }

    # Where each alert points, as a time the page can open the asset at.
    shown_alerts = []
    for a in alerts or []:
        a = dict(a)
        when = pd.to_datetime(a.get("at"), errors="coerce") if a.get("at") else None
        a["at"] = when.strftime("%Y-%m-%dT%H:%M") if when is not None else None
        shown_alerts.append(a)

    def page(sub_df: pd.DataFrame) -> str:
        data = (
            _block("ds-scores", _csv(main))
            + _block("ds-subsys", _csv(sub_df))
            + _block("ds-failures", _csv(fail_rows))
            + _block("ds-bands", _csv(band_rows))
            + _block("ds-weights", _csv(weight_rows))
            + _block("ds-runs", _csv(run_rows) if len(run_rows) else "")
            + _block("ds-changes", _csv(change_rows) if len(change_rows) else "")
            + _block(
                "ds-alerts",
                json.dumps(shown_alerts, default=str).replace("</", "<\\/"),
                "application/json",
            )
            + _block(
                "ds-logs",
                json.dumps(log_data).replace("</", "<\\/"),
                "application/json",
            )
            + _block(
                "ds-meta", json.dumps(meta).replace("</", "<\\/"), "application/json"
            )
        )
        html = _template().replace("{{TITLE}}", title.replace("<", "&lt;"))
        return html.replace("<!--DATA-->", data)

    html = page(subsys)
    if len(html.encode()) > MAX_BYTES and len(subsys):
        # Keep the page under 10 MB: keep the highest subsystem values only.
        keep = int(len(subsys) * MAX_BYTES / len(html.encode()) * 0.9)
        html = page(subsys.nlargest(keep, "risk").sort_values(["asset_id", "t"]))

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    return out
