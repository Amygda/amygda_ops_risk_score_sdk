"""Alerts: rules checked after every run, and the alerts they raise.

Rules are chosen in the app spec (``app.json``)::

    "alerts": {"rules": [
        {"type": "enters_band", "band": "high"},
        {"type": "rises_by", "points": 10},
        {"type": "no_data", "days": 7},
        {"type": "run_failed", "runs": 1},
        {"type": "unmatched_above", "percent": 30}
    ]}

Alerts are kept in the monitor's storage (``alerts/alerts.json``, or the
``alerts`` table of ``monitor.db``). An alert is
``open`` until someone acknowledges it. While it is open, the same thing
happening again updates it instead of adding another. Alerts about a state
(a failed run, a quiet asset, too many unmatched logs) are ``cleared`` by
themselves when a later run shows the state has ended.

An alert's ``message`` says what happened and when in the data. The same time
is kept in ``at`` (the period to look at), so the page can open the asset
there.
"""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from amygda_ops_risk_score.monitor.store import ALERTS_FILE  # noqa: F401
from amygda_ops_risk_score.monitor.store import FileStore

KEEP = 2000  # closed alerts beyond this are dropped, oldest first
_RANK = {"normal": 0, "watch": 1, "high": 2}

# Each rule takes one setting.
RULES: Dict[str, Dict[str, Any]] = {
    "enters_band": {
        "says": "An asset's score reaches watch or high in a run.",
        "setting": "band",
        "choices": ("watch", "high"),
        "default": "high",
    },
    "rises_by": {
        "says": "An asset's latest score rose by at least this many points in a run.",
        "setting": "points",
        "default": 10,
        "range": (1, 100),
    },
    "no_data": {
        "says": "An asset has had no logs for this many days, while others have.",
        "setting": "days",
        "default": 7,
        "range": (1, 365),
    },
    "run_failed": {
        "says": "This many runs in a row have failed.",
        "setting": "runs",
        "default": 1,
        "range": (1, 50),
    },
    "unmatched_above": {
        "says": "More than this percentage of a run's new logs matched no subsystem.",
        "setting": "percent",
        "default": 30,
        "range": (1, 100),
    },
}
DEFAULT_RULES = [{"type": "enters_band", "band": "high"}, {"type": "run_failed"}]


def validate_rules(alerts: Any, error=ValueError) -> Dict[str, Any]:
    """Check the ``alerts`` part of a spec; fill in defaults.

    Left out, the default rules apply; ``{"rules": []}`` turns alerts off.
    """
    if alerts is None:
        alerts = {"rules": DEFAULT_RULES}
    if not isinstance(alerts, dict) or set(alerts) - {"rules"}:
        raise error('"alerts" must be an object with a "rules" list.')
    rules = alerts.get("rules", DEFAULT_RULES)
    if not isinstance(rules, list):
        raise error('"alerts.rules" must be a list.')
    out, seen = [], set()
    for raw in rules:
        if not isinstance(raw, dict) or raw.get("type") not in RULES:
            got = raw.get("type") if isinstance(raw, dict) else raw
            raise error(f'Unknown alert rule "{got}". Choose from: {", ".join(RULES)}.')
        kind = raw["type"]
        info = RULES[kind]
        name = info["setting"]
        extra = set(raw) - {"type", name}
        if extra:
            raise error(
                f'The {kind} alert rule takes only "{name}" '
                f'(got "{sorted(extra)[0]}").'
            )
        value = raw.get(name, info["default"])
        if "choices" in info:
            if value not in info["choices"]:
                raise error(
                    f'"{name}" on the {kind} alert rule must be one of: '
                    f'{", ".join(info["choices"])}.'
                )
        else:
            low, high = info["range"]
            ok = isinstance(value, (int, float)) and not isinstance(value, bool)
            if not ok or not low <= value <= high:
                raise error(
                    f'"{name}" on the {kind} alert rule must be a number from '
                    f"{low} to {high}."
                )
        key = f"{kind}:{value}" if kind == "enters_band" else kind
        if key in seen:
            raise error(f"The {kind} alert rule is listed twice.")
        seen.add(key)
        out.append({"type": kind, name: value})
    return {"rules": out}


def _fmt(ts: Any) -> str:
    t = pd.Timestamp(ts)
    return f"{t:%b} {t.day}, {t:%Y %H:%M}"


_WORDS = {
    "enters_band": ("An asset reaches", ""),
    "rises_by": ("An asset's score rises by", "points or more in one run"),
    "no_data": ("An asset has no logs for", "days, while others have"),
    "run_failed": ("This many runs in a row fail:", ""),
    "unmatched_above": ("More than", "% of a run's new logs match nothing"),
}


def settings(rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Every kind of rule as one line for a settings form: whether it is on,
    its one value, and the words before and after it."""
    out = []
    for kind, info in RULES.items():
        mine = [r for r in rules if r["type"] == kind]
        name = info["setting"]
        value = info["default"]
        if mine:
            value = mine[0][name]
            if kind == "enters_band" and any(r[name] == "watch" for r in mine):
                value = "watch"  # watch covers high
        line = {
            "type": kind,
            "on": bool(mine),
            "setting": name,
            "value": value,
            "before": _WORDS[kind][0],
            "after": _WORDS[kind][1],
        }
        if "choices" in info:
            line["choices"] = [
                {"value": "high", "label": "high"},
                {"value": "watch", "label": "watch or high"},
            ]
        else:
            line["min"], line["max"] = info["range"]
        out.append(line)
    return out


def describe_rule(rule: Dict[str, Any]) -> str:
    """A rule in plain words, for the dashboard."""
    kind = rule["type"]
    if kind == "enters_band":
        both = " or high" if rule["band"] == "watch" else ""
        return f"an asset reaches {rule['band']}{both}"
    if kind == "rises_by":
        return f"an asset's score rises by {rule['points']:g} or more in a run"
    if kind == "no_data":
        d = rule["days"]
        return f"an asset has no logs for {d:g} day{'' if d == 1 else 's'}"
    if kind == "run_failed":
        n = rule["runs"]
        return "a run fails" if n == 1 else f"{n} runs in a row fail"
    return f"more than {rule['percent']:g}% of a run's new logs match no subsystem"


def findings_for_run(
    rules: List[Dict[str, Any]],
    record: Dict[str, Any],
    scores: pd.DataFrame,
    failed_in_a_row: int = 0,
) -> tuple:
    """What a run's record means for each rule.

    Returns ``(findings, checked)``. ``findings`` are alerts to raise or
    update. ``checked`` lists the state rules this run could judge: an open
    alert of theirs that is not among the findings has ended, and is cleared.
    """
    findings: List[Dict[str, Any]] = []
    checked: List[str] = []
    status = record.get("status")
    bands = record.get("bands") or {}
    by = {r["type"]: r for r in rules if r["type"] != "enters_band"}
    band_rules = sorted(
        (r["band"] for r in rules if r["type"] == "enters_band"),
        key=lambda b: _RANK[b],
    )

    if "run_failed" in by:
        if status == "failed":
            need = by["run_failed"]["runs"]
            if failed_in_a_row >= need:
                n = failed_in_a_row
                lead = "The last run failed" if n == 1 else f"The last {n} runs failed"
                findings.append(
                    {
                        "rule": "run_failed",
                        "asset_id": None,
                        "severity": "high",
                        "message": f"{lead}. {record.get('reason') or ''}".strip(),
                        "value": n,
                    }
                )
        else:
            checked.append("run_failed")  # a run got through

    if status != "ok":
        return findings, checked

    if band_rules:
        lowest = band_rules[0]
        for c in record.get("changes") or []:
            reached = c.get("band_of_highest") or "normal"
            before = c.get("band_before_run") or "normal"
            if _RANK[reached] < _RANK[lowest] or _RANK[reached] <= _RANK[before]:
                continue  # below every rule, or it was already there
            if reached not in band_rules and lowest != "watch":
                continue
            cut = bands.get(reached)
            findings.append(
                {
                    "rule": f"enters_band:{reached}",
                    "asset_id": c["asset_id"],
                    "severity": reached,
                    "message": f"{c['asset_id']} reached {reached}: "
                    f"{c['highest_this_run']:.1f} on "
                    f"{_fmt(c['highest_this_run_at'])}"
                    + (f" ({reached} is {cut:g} or more)." if cut else "."),
                    "value": round(float(c["highest_this_run"]), 1),
                    "at": str(c["highest_this_run_at"]),
                }
            )

    if "rises_by" in by:
        points = by["rises_by"]["points"]
        for c in record.get("changes") or []:
            change = c.get("change")
            if change is not None and change >= points:
                findings.append(
                    {
                        "rule": "rises_by",
                        "asset_id": c["asset_id"],
                        "severity": "watch",
                        "message": f"{c['asset_id']} rose by {change:.1f} to "
                        f"{c['score_now']:.1f} in one run"
                        + (
                            f", on {_fmt(c['last_period'])}."
                            if c.get("last_period")
                            else "."
                        ),
                        "value": round(float(change), 1),
                        "at": c.get("last_period"),
                    }
                )

    if "unmatched_above" in by:
        checked.append("unmatched_above")
        share = record.get("unmatched_share")
        percent = by["unmatched_above"]["percent"]
        if share is not None and share * 100 > percent:
            findings.append(
                {
                    "rule": "unmatched_above",
                    "asset_id": None,
                    "severity": "watch",
                    "message": f"{share:.0%} of the new logs in the last run matched "
                    f"no subsystem (the limit is {percent:g}%). The data may have "
                    "changed since the model was trained.",
                    "value": round(share * 100, 1),
                }
            )

    if "no_data" in by and len(scores):
        checked.append("no_data")
        days = by["no_data"]["days"]
        last = pd.to_datetime(scores["period_start"]).groupby(scores["asset_id"]).max()
        newest = last.max()
        for asset, when in last[last < newest - pd.Timedelta(days=days)].items():
            quiet = (newest - when).days
            findings.append(
                {
                    "rule": "no_data",
                    "asset_id": str(asset),
                    "severity": "watch",
                    "message": f"{asset} has had no logs since {_fmt(when)}: "
                    f"{quiet} day{'' if quiet == 1 else 's'}, while other "
                    "assets have.",
                    "value": quiet,
                    "at": str(when),
                }
            )
    return findings, checked


class AlertStore:
    """The alerts of one monitor. ``store`` is the monitor's store
    (``Monitor.store``) or a monitor folder that keeps its data in files."""

    def __init__(self, store):
        if not hasattr(store, "save_alerts"):
            store = FileStore(Path(store))
        self.store = store

    def all(self) -> List[Dict[str, Any]]:
        """Every alert, oldest first."""
        return self.store.alerts()

    def _save(self, alerts: List[Dict[str, Any]]) -> None:
        closed = [a for a in alerts if a["status"] != "open"]
        if len(closed) > KEEP:
            drop = {a["id"] for a in closed[: len(closed) - KEEP]}
            alerts = [a for a in alerts if a["id"] not in drop]
        self.store.save_alerts(alerts)

    def apply(
        self,
        findings: List[Dict[str, Any]],
        checked: List[str],
        run_id: str,
        now: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Record a run's findings. Returns the alerts newly raised."""
        when = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
        alerts = self.all()
        open_by = {
            (a["rule"], a.get("asset_id")): a for a in alerts if a["status"] == "open"
        }
        number = max((a.get("number", 0) for a in alerts), default=0)
        raised, found = [], set()
        for f in findings:
            ident = (f["rule"], f.get("asset_id"))
            found.add(ident)
            current = open_by.get(ident)
            if current:
                current.update(
                    message=f["message"],
                    value=f["value"],
                    at=f.get("at"),
                    last_seen_at=when,
                    last_run_id=run_id,
                    times=current.get("times", 1) + 1,
                )
                continue
            number += 1
            alert = dict(
                f,
                id=f"a{number}",
                number=number,
                status="open",
                raised_at=when,
                last_seen_at=when,
                run_id=run_id,
                last_run_id=run_id,
                times=1,
            )
            alerts.append(alert)
            open_by[ident] = alert
            raised.append(alert)
        for ident, alert in open_by.items():
            if alert["rule"] in checked and ident not in found:
                alert.update(status="cleared", closed_at=when, closed_by_run=run_id)
        if findings or raised or any(a.get("closed_at") == when for a in alerts):
            self._save(alerts)
        return raised

    def acknowledge(self, alert_id: Optional[str] = None) -> int:
        """Acknowledge one open alert, or all of them. Returns how many."""
        when = datetime.now(timezone.utc).isoformat(timespec="seconds")
        alerts = self.all()
        n = 0
        for a in alerts:
            if a["status"] == "open" and alert_id in (None, a["id"]):
                a.update(status="acknowledged", closed_at=when)
                n += 1
        if n:
            self._save(alerts)
        return n
