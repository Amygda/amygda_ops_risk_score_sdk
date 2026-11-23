"""What the fleet app shows: one JSON spec of tabs, panels and header tiles.

The spec lives in ``app.json`` in the monitor folder. It only chooses and
arranges panels from the catalogue below; it holds no code. The dashboard
(and the app that serves it) is laid out from it::

    {
      "title": "Conveyor fleet",
      "rank_by": "peak",
      "theme": {"accent": "#0b6e4f", "logo": "logo.png", "mode": "light"},
      "header": {"tiles": ["assets_high_now", "highest", "last_run"]},
      "tabs": [
        {"title": "Fleet", "panels": ["heatmap", {"type": "ranking", "top": 20}]},
        {"title": "Asset", "panels": ["asset_trend", "asset_drivers"]}
      ]
    }

``validate_spec`` fills in every default and explains what is wrong in plain
words; ``catalogue()`` lists what can be chosen.
"""

from __future__ import annotations

import copy
import difflib
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Union

from amygda_ops_risk_score.monitor.alerts import RULES as ALERT_RULES
from amygda_ops_risk_score.monitor.alerts import validate_rules

FORMAT_VERSION = 1
SPEC_FILE = "app.json"
MAX_TABS = 8
MAX_TILES = 6
MAX_LOGO_BYTES = 300 * 1024
SCHEDULE_HOURS = (1, 2, 3, 4, 6, 8, 12)
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
LOGO_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


class SpecError(ValueError):
    """The app spec is not valid. The message says what to change."""


_RANKING_COLUMNS = [
    "mean",
    "p90",
    "peak",
    "peak_time",
    "latest",
    "at_watch",
    "at_high",
    "failures",
]

# needs: "runs" = the monitor has run at least once; "model" = model details
# that only some models have. Without them the panel is left out (or shown as
# a placeholder in a preview).
PANELS: Dict[str, Dict[str, Any]] = {
    "since_last_run": {
        "title": "Since the last run",
        "shows": "Assets scored in the latest run: score now, the change, the "
        "highest risk in that run and the time range scored.",
        "needs": "runs",
        "options": {
            "only_flagged": {
                "type": "bool",
                "default": False,
                "help": "List only assets that reached watch or high.",
            }
        },
    },
    "heatmap": {
        "title": "Risk by asset and day",
        "shows": "A grid of assets by day, coloured by risk; failures outlined.",
        "options": {
            "max_rows": {
                "type": "int",
                "default": 40,
                "min": 5,
                "max": 200,
                "help": "Most assets to draw before only the highest-ranked "
                "are shown.",
            }
        },
    },
    "ranking": {
        "title": "Ranking",
        "shows": "A table of assets, highest risk first.",
        "options": {
            "columns": {
                "type": "list",
                "choices": _RANKING_COLUMNS,
                "default": list(_RANKING_COLUMNS),
                "help": "Columns to show, in this order.",
            },
            "top": {
                "type": "int",
                "default": None,
                "min": 1,
                "max": 10000,
                "help": "Show only the first N assets (default: all).",
            },
        },
    },
    "fleet_systems": {
        "title": "Risk by asset and system",
        "shows": "A table of assets by system, to see which system is behind "
        "each asset's risk. The overall score is coloured by the alert bands.",
        "options": {
            "value": {
                "type": "choice",
                "choices": ["latest", "peak", "mean"],
                "default": "latest",
                "help": "Which figure each cell shows.",
            }
        },
    },
    "asset_trend": {
        "title": "Operational risk over time",
        "shows": "One asset's risk over time, with bands and failures; drag "
        "to zoom.",
        "options": {},
    },
    "asset_systems": {
        "title": "Risk by system",
        "shows": "One asset's risk over time, a row per system.",
        "width": "half",
        "options": {},
    },
    "asset_drivers": {
        "title": "What drove the selected period",
        "shows": "The subsystems behind one asset's score in one period.",
        "width": "half",
        "options": {},
    },
    "asset_logs": {
        "title": "Logs behind the score",
        "shows": "One asset's logs: how many there were over time, and a "
        "table of the logs behind the selected score. A saved page with this "
        "panel contains the log text.",
        "needs": "logs",
        "options": {
            "max_rows": {
                "type": "int",
                "default": 300,
                "min": 10,
                "max": 5000,
                "help": "Most kinds of log to list in the table.",
            }
        },
    },
    "bands": {
        "title": "Alert bands",
        "shows": "The watch and high cut-offs and how they were set.",
        "width": "half",
        "options": {},
    },
    "weights": {
        "title": "What the score is made of",
        "shows": "Each subsystem's share of the overall score.",
        "needs": "model",
        "width": "half",
        "options": {},
    },
    "unmapped_codes": {
        "title": "Log codes the model doesn't use",
        "shows": "Codes from training that map to no subsystem (fixed-log "
        "models only).",
        "needs": "model",
        "options": {},
    },
    "known_gaps": {
        "title": "Known gaps",
        "shows": "What the scores don't cover, in plain sentences.",
        "options": {},
    },
    "run_health": {
        "title": "Run health",
        "shows": "Four figures: the last run, run counts, logs with no match "
        "and provisional periods.",
        "needs": "runs",
        "options": {},
    },
    "run_warnings": {
        "title": "Warnings in the last run",
        "shows": "Warnings from the last run, or why it failed.",
        "needs": "runs",
        "options": {},
    },
    "alerts": {
        "title": "Alerts",
        "shows": "Alerts raised by the rules you chose, open ones first. In "
        "the app they can be acknowledged.",
        "needs": "runs",
        "options": {
            "include_closed": {
                "type": "bool",
                "default": True,
                "help": "Also list acknowledged and cleared alerts.",
            },
            "limit": {
                "type": "int",
                "default": 50,
                "min": 1,
                "max": 2000,
                "help": "Most alerts to list.",
            },
        },
    },
    "run_table": {
        "title": "Every run",
        "shows": "Every run: when, manual or scheduled, status and counts.",
        "needs": "runs",
        "options": {
            "limit": {
                "type": "int",
                "default": None,
                "min": 1,
                "max": 10000,
                "help": "Show only the newest N runs (default: all).",
            }
        },
    },
}

TILES: Dict[str, str] = {
    "assets_high": "Assets that reached high in the period shown",
    "assets_high_now": "Assets whose latest score is high",
    "assets_watch_now": "Assets whose latest score is watch or high",
    "median": "Fleet median risk",
    "highest": "Highest risk, with the asset and time",
    "at_watch": "Asset-days (or periods) at watch, and how many were high",
    "assets_scored": "Assets and periods scored",
    "last_run": "Last run: status and when (needs a run)",
    "unmatched": "Share of new logs matching no subsystem (needs a run)",
    "provisional": "Periods still waiting for data",
    "open_alerts": "Open alerts (needs a run)",
}

RANK_BY = {
    "mean": "average risk",
    "p90": "90th percentile risk",
    "peak": "peak risk",
    "latest": "latest score",
}

_DEFAULT_TILES = ["assets_high", "median", "highest", "at_watch"]
_DEFAULT_TABS = [
    {
        "id": "fleet",
        "title": "Fleet",
        "panels": ["since_last_run", "heatmap", "ranking"],
    },
    {
        "id": "asset",
        "title": "Asset detail",
        "panels": ["asset_trend", "asset_systems", "asset_drivers", "asset_logs"],
    },
    {"id": "alerts", "title": "Alerts", "panels": ["alerts"]},
    {
        "id": "model",
        "title": "Model",
        "panels": ["bands", "weights", "unmapped_codes", "known_gaps"],
    },
    {
        "id": "runs",
        "title": "Runs",
        "panels": ["run_health", "run_warnings", "run_table"],
    },
]
_TOP_KEYS = {
    "format_version",
    "title",
    "rank_by",
    "days",
    "notes",
    "theme",
    "schedule",
    "alerts",
    "default_tab",
    "header",
    "tabs",
}
_PANEL_KEYS = {"type", "title", "width", "hidden"}


def default_spec() -> Dict[str, Any]:
    """The standard layout: Fleet, Asset detail, Model and Runs."""
    return validate_spec({})


def catalogue() -> Dict[str, Any]:
    """Everything a spec can choose from, for an agent or a person to read."""
    return {
        "panels": copy.deepcopy(PANELS),
        "tiles": dict(TILES),
        "rank_by": dict(RANK_BY),
        "settings": {
            "title": "Name shown at the top, as written (default: the monitor's "
            'fleet name followed by "risk").',
            "rank_by": "How assets are ordered everywhere: "
            + ", ".join(RANK_BY)
            + " (default mean).",
            "days": "Show only the most recent N days (default: the monitor's "
            "setting, 90).",
            "notes": 'Where each panel\'s explanation goes: "tooltip" (an info '
            'mark next to the title, the default), "inline" (written under '
            'the title) or "off".',
            "header.facts": "false hides the line of key settings under the "
            "title (watch and high levels, how often scores are made, the "
            "dates covered, the model type).",
            "alerts.rules": "What raises an alert after a run. Each rule has "
            'a "type" and one setting: '
            + "; ".join(
                f'{name} ("{r["setting"]}", default {r["default"]}): {r["says"]}'
                for name, r in ALERT_RULES.items()
            )
            + " Left out: an asset reaching high, and a failed run. An empty "
            "list turns alerts off.",
            "schedule": "When the app runs the monitor by itself: every N "
            "hours, every day at a time, or every week on a day at a time. "
            "Only the app (amygda-risk app) acts on it.",
            "theme.mode": "auto (follow the viewer's device, the default), light "
            "or dark.",
            "theme.accent": 'A brand colour as "#rrggbb", used for the bar at '
            "the top and the open tab. Amber and red stay as they are: they "
            "mean watch and high.",
            "theme.logo": "An image file (png, jpg, svg, gif or webp, up to "
            f"{MAX_LOGO_BYTES // 1024} KB) shown next to the title.",
            "default_tab": "The tab that opens first (default: the first tab).",
            "header.takeaway": "false hides the one-sentence summary.",
            "header.tiles": f"Up to {MAX_TILES} tiles, in order.",
        },
        "rules": [
            "Each panel can appear once.",
            "The asset_* panels share one asset selector, so they go on the "
            "same tab.",
            f"Up to {MAX_TABS} tabs; a tab needs at least one panel.",
            'A panel is a name ("heatmap") or an object with "type", an '
            'optional "title", "width" ("full" or "half") and its options.',
        ],
    }


# The panels as a person would choose them: group by group, each with a plain
# name and a line saying what they would see. Used by ``amygda-risk panels
# --menu`` and by the agent skill, so every user is asked in the same words.
MENU: List[Dict[str, Any]] = [
    {
        "group": "The whole fleet",
        "asks": "What do you want to see about the fleet as a whole?",
        "panels": [
            (
                "since_last_run",
                "What changed in the latest run",
                "Each asset's score now, how far it moved, and the highest "
                "it reached in the new data.",
            ),
            (
                "ranking",
                "Ranking of assets",
                "A table of every asset, the riskiest first.",
            ),
            (
                "heatmap",
                "Heatmap",
                "A grid of assets by day, coloured by risk, to see how risk "
                "moved over the weeks.",
            ),
            (
                "fleet_systems",
                "Risk by system",
                "A table of assets against systems, to see which system is "
                "behind each asset's risk.",
            ),
        ],
    },
    {
        "group": "One asset in detail",
        "asks": "When you pick one asset, what do you want to see about it?",
        "panels": [
            (
                "asset_trend",
                "Risk over time",
                "The asset's risk as a line, with the watch and high levels "
                "and any failures marked.",
            ),
            (
                "asset_systems",
                "Each system over time",
                "The same period split into one row per system.",
            ),
            (
                "asset_drivers",
                "What drove a period",
                "The subsystems behind the asset's score at a time you pick.",
            ),
            (
                "asset_logs",
                "The logs behind the score",
                "How many logs the asset had over time, and a table of the "
                "actual logs behind the score you pick.",
            ),
        ],
    },
    {
        "group": "Alerts",
        "asks": "Do you want a list of alerts on the page?",
        "panels": [
            (
                "alerts",
                "Alerts list",
                "Alerts raised by your rules, open ones first, with a button "
                "to acknowledge them.",
            ),
        ],
    },
    {
        "group": "How the model works",
        "asks": "Do you want the page to explain the model behind the scores?",
        "panels": [
            (
                "bands",
                "Watch and high levels",
                "The two levels and how they were set.",
            ),
            (
                "weights",
                "What the score is made of",
                "How much each subsystem counts toward the overall score.",
            ),
            (
                "unmapped_codes",
                "Log codes the model doesn't use",
                "Codes from the training data that never affect a score "
                "(fixed-log models only).",
            ),
            (
                "known_gaps",
                "Known gaps",
                "What the scores don't cover, in plain sentences.",
            ),
        ],
    },
    {
        "group": "How the runs went",
        "asks": "Do you want to see how the scoring runs went?",
        "panels": [
            (
                "run_health",
                "Run health",
                "Four figures: the last run, how many runs, logs with no "
                "match, and periods still waiting for data.",
            ),
            (
                "run_warnings",
                "Warnings in the last run",
                "Anything the last run warned about, or why it failed.",
            ),
            (
                "run_table",
                "Every run",
                "A table of every run: when, the dates its data covered, "
                "and the counts.",
            ),
        ],
    },
]


def menu() -> List[Dict[str, Any]]:
    """The panels grouped for choosing: a list of groups, each with the
    question to ask and its panels (``type``, ``name``, ``shows``)."""
    return [
        {
            "group": g["group"],
            "asks": g["asks"],
            "panels": [
                {"type": kind, "name": name, "shows": shows}
                for kind, name, shows in g["panels"]
            ],
        }
        for g in MENU
    ]


def describe_menu() -> str:
    """The panels as a pick list, group by group (``amygda-risk panels
    --menu``)."""
    lines = ["Choose the panels for your app, one group at a time.", ""]
    for n, g in enumerate(MENU, 1):
        lines.append(f"{n}. {g['group']}: {g['asks']}")
        for letter, (kind, name, shows) in zip("abcdefgh", g["panels"]):
            lines.append(f"   {n}{letter}. {name}  ({kind})")
            lines.append(f"       {shows}")
        lines.append("")
    lines.append('Answer each group with its letters, "all" or "none".')
    return "\n".join(lines)


def describe_catalogue() -> str:
    """The catalogue as plain text (``amygda-risk panels``)."""
    lines = ["Panels:"]
    for name, p in PANELS.items():
        needs = {
            "runs": " [after the first run]",
            "model": " [if the model has it]",
            "logs": " [once logs are kept]",
        }
        lines.append(f"  {name:<16} {p['shows']}{needs.get(p.get('needs'), '')}")
        for opt, o in p["options"].items():
            lines.append(f"  {'':<16}   {opt}: {o['help']}")
    lines.append("")
    lines.append("Header tiles:")
    lines += [f"  {name:<16} {text}" for name, text in TILES.items()]
    lines.append("")
    lines.append("Settings:")
    cat = catalogue()
    lines += [f"  {name:<16} {text}" for name, text in cat["settings"].items()]
    lines.append("")
    lines.append("Rules:")
    lines += [f"  - {r}" for r in cat["rules"]]
    return "\n".join(lines)


def _unknown(what: str, value: Any, known) -> SpecError:
    near = difflib.get_close_matches(str(value), list(known), n=1)
    hint = f' Did you mean "{near[0]}"?' if near else ""
    return SpecError(
        f'Unknown {what} "{value}".{hint} Choose from: {", ".join(sorted(known))}.'
    )


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


def _option(panel: str, name: str, rule: Dict[str, Any], value: Any) -> Any:
    where = f'"{name}" on the {panel} panel'
    kind = rule["type"]
    if value is None:
        if rule["default"] is None:
            return None
        raise SpecError(f"{where} can't be empty.")
    if kind == "bool":
        if not isinstance(value, bool):
            raise SpecError(f"{where} must be true or false.")
        return value
    if kind == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise SpecError(f"{where} must be a whole number.")
        if not rule["min"] <= value <= rule["max"]:
            raise SpecError(f"{where} must be between {rule['min']} and {rule['max']}.")
        return value
    if kind == "choice":
        if value not in rule["choices"]:
            raise _unknown(f"value for {where}:", value, rule["choices"])
        return value
    if not isinstance(value, list) or not value:
        raise SpecError(f"{where} must be a list with at least one entry.")
    for v in value:
        if v not in rule["choices"]:
            raise _unknown(f"entry in {where}:", v, rule["choices"])
    if len(set(value)) != len(value):
        raise SpecError(f"{where} lists an entry twice.")
    return list(value)


def _panel(entry: Any) -> Dict[str, Any]:
    if isinstance(entry, str):
        entry = {"type": entry}
    if not isinstance(entry, dict) or "type" not in entry:
        raise SpecError(
            'Each panel must be a name ("heatmap") or an object with a "type".'
        )
    kind = entry["type"]
    if kind not in PANELS:
        raise _unknown("panel", kind, PANELS)
    rules = PANELS[kind]["options"]
    # A saved spec keeps options under "options"; hand-written ones may put
    # them next to "type". Both are read.
    nested = entry.get("options") or {}
    if not isinstance(nested, dict):
        raise SpecError(f'"options" on the {kind} panel must be an object.')
    entry = {**nested, **{k: v for k, v in entry.items() if k != "options"}}
    for key in entry:
        if key not in _PANEL_KEYS and key not in rules:
            raise _unknown(
                f"setting on the {kind} panel:", key, _PANEL_KEYS | set(rules)
            )
    title = entry.get("title")
    if title is not None and (not isinstance(title, str) or not title.strip()):
        raise SpecError(f"The title of the {kind} panel must be some text.")
    width = entry.get("width", PANELS[kind].get("width", "full"))
    if width not in ("full", "half"):
        raise SpecError(f'The width of the {kind} panel must be "full" or "half".')
    hidden = entry.get("hidden", False)
    if not isinstance(hidden, bool):
        raise SpecError(f'"hidden" on the {kind} panel must be true or false.')
    return {
        "type": kind,
        "title": title.strip() if title else None,
        "width": width,
        # Switched off in the app's settings: it keeps its place in the
        # layout but is not shown.
        "hidden": hidden,
        "options": {
            name: _option(kind, name, rule, entry.get(name, rule["default"]))
            for name, rule in rules.items()
        },
    }


def validate_spec(spec: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Check a spec and return it with every default filled in.

    Raises :class:`SpecError` with a plain message when something is wrong.
    """
    spec = {} if spec is None else spec
    if not isinstance(spec, dict):
        raise SpecError("The app spec must be a JSON object.")
    for key in spec:
        if key not in _TOP_KEYS:
            raise _unknown("setting", key, _TOP_KEYS)
    if spec.get("format_version", FORMAT_VERSION) != FORMAT_VERSION:
        raise SpecError(
            f"This app spec is format {spec['format_version']}; this version of "
            f"the SDK reads format {FORMAT_VERSION}. Upgrade the SDK."
        )

    title = spec.get("title")
    if title is not None and (not isinstance(title, str) or not title.strip()):
        raise SpecError('"title" must be some text.')
    rank_by = spec.get("rank_by", "mean")
    if rank_by not in RANK_BY:
        raise _unknown('"rank_by"', rank_by, RANK_BY)
    days = spec.get("days")
    if days is not None and (
        isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 3650
    ):
        raise SpecError('"days" must be a whole number from 1 to 3650.')
    notes = spec.get("notes", "tooltip")
    notes = {True: "tooltip", False: "off"}.get(notes, notes)  # the first form
    if notes not in ("tooltip", "inline", "off"):
        raise SpecError('"notes" must be "tooltip", "inline" or "off".')

    theme = spec.get("theme") or {}
    if not isinstance(theme, dict):
        raise SpecError('"theme" must be an object.')
    for key in theme:
        if key not in ("mode", "accent", "logo"):
            raise _unknown("theme setting", key, ("mode", "accent", "logo"))
    mode = theme.get("mode") or "auto"
    if mode not in ("auto", "light", "dark"):
        raise _unknown('"theme.mode"', mode, ("auto", "light", "dark"))
    accent = theme.get("accent")
    if accent is not None and (
        not isinstance(accent, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", accent)
    ):
        raise SpecError(
            '"theme.accent" must be a colour like "#0b6e4f" (# and six hex digits).'
        )
    logo = theme.get("logo")
    if logo is not None:
        if not isinstance(logo, str) or not logo.strip():
            raise SpecError('"theme.logo" must be the path of an image file.')
        if Path(logo).suffix.lower() not in LOGO_TYPES:
            raise SpecError(
                '"theme.logo" must be a png, jpg, svg, gif or webp file '
                f'(got "{Path(logo).name}").'
            )

    header = spec.get("header", {})
    if not isinstance(header, dict):
        raise SpecError('"header" must be an object.')
    for key in header:
        if key not in ("takeaway", "facts", "tiles"):
            raise _unknown("header setting", key, ("takeaway", "facts", "tiles"))
    takeaway = header.get("takeaway", True)
    if not isinstance(takeaway, bool):
        raise SpecError('"header.takeaway" must be true or false.')
    facts = header.get("facts", True)
    if not isinstance(facts, bool):
        raise SpecError('"header.facts" must be true or false.')
    tiles = header.get("tiles", _DEFAULT_TILES)
    if not isinstance(tiles, list) or len(tiles) > MAX_TILES:
        raise SpecError(f'"header.tiles" must be a list of up to {MAX_TILES} tiles.')
    for t in tiles:
        if t not in TILES:
            raise _unknown("tile", t, TILES)
    if len(set(tiles)) != len(tiles):
        raise SpecError('"header.tiles" lists a tile twice.')

    raw_tabs = spec.get("tabs", _DEFAULT_TABS)
    if not isinstance(raw_tabs, list) or not 1 <= len(raw_tabs) <= MAX_TABS:
        raise SpecError(f'"tabs" must be a list of 1 to {MAX_TABS} tabs.')
    tabs: List[Dict[str, Any]] = []
    seen: Dict[str, str] = {}
    asset_tab = None
    for i, raw in enumerate(raw_tabs, 1):
        if not isinstance(raw, dict):
            raise SpecError(f"Tab {i} must be an object with a title and panels.")
        for key in raw:
            if key not in ("id", "title", "panels", "hidden"):
                raise _unknown(
                    f"setting on tab {i}:", key, ("id", "title", "panels", "hidden")
                )
        if not isinstance(raw.get("hidden", False), bool):
            raise SpecError(f'"hidden" on tab {i} must be true or false.')
        tab_title = raw.get("title")
        if not isinstance(tab_title, str) or not tab_title.strip():
            raise SpecError(f"Tab {i} needs a title.")
        tab_id = _slug(raw.get("id") or tab_title)
        if not tab_id:
            raise SpecError(
                f'Tab {i} ("{tab_title}") needs an id of letters or digits.'
            )
        if any(t["id"] == tab_id for t in tabs):
            raise SpecError(f'Two tabs are called "{tab_id}". Give one another title.')
        panels = raw.get("panels")
        if not isinstance(panels, list) or not panels:
            raise SpecError(f'The "{tab_title}" tab needs at least one panel.')
        out = []
        for entry in panels:
            p = _panel(entry)
            if p["type"] in seen:
                raise SpecError(
                    f'The {p["type"]} panel is on both the "{seen[p["type"]]}" and '
                    f'"{tab_title}" tabs. Each panel can appear once.'
                )
            seen[p["type"]] = tab_title
            if p["type"].startswith("asset_"):
                if asset_tab not in (None, tab_title):
                    raise SpecError(
                        "The asset_* panels share one asset selector, so they "
                        f'must be on the same tab (found on "{asset_tab}" and '
                        f'"{tab_title}").'
                    )
                asset_tab = tab_title
            out.append(p)
        tabs.append(
            {
                "id": tab_id,
                "title": tab_title.strip(),
                "hidden": raw.get("hidden", False),
                "panels": out,
            }
        )

    schedule = validate_schedule(spec.get("schedule"))
    alerts = validate_rules(spec.get("alerts"), error=SpecError)

    default_tab = spec.get("default_tab")
    if default_tab is None:
        default_tab = tabs[0]["id"]
    else:
        match = [t["id"] for t in tabs if default_tab in (t["id"], t["title"])]
        if not match:
            raise _unknown('"default_tab"', default_tab, [t["id"] for t in tabs])
        default_tab = match[0]

    return {
        "format_version": FORMAT_VERSION,
        "title": title.strip() if title else None,
        "rank_by": rank_by,
        "days": days,
        "notes": notes,
        "theme": {
            "mode": mode,
            "accent": accent.lower() if accent else None,
            "logo": logo.strip() if logo else None,
        },
        "schedule": schedule,
        "alerts": alerts,
        "default_tab": default_tab,
        "header": {"takeaway": takeaway, "facts": facts, "tiles": list(tiles)},
        "tabs": tabs,
    }


def validate_schedule(schedule: Any) -> Optional[Dict[str, Any]]:
    """Check when the app runs the monitor by itself. None means never.

    ``{"every": "hours", "hours": 6}``, ``{"every": "day", "at": "06:00"}`` or
    ``{"every": "week", "weekday": "mon", "at": "06:00"}``; ``"paused": true``
    keeps the schedule but stops it firing. Times are this machine's local time.
    """
    if schedule is None:
        return None
    if not isinstance(schedule, dict):
        raise SpecError('"schedule" must be an object, or null for no schedule.')
    keys = ("every", "hours", "at", "weekday", "paused")
    for key in schedule:
        if key not in keys:
            raise _unknown("schedule setting", key, keys)
    every = schedule.get("every")
    if every not in ("hours", "day", "week"):
        raise SpecError('"schedule.every" must be "hours", "day" or "week".')
    paused = schedule.get("paused", False)
    if not isinstance(paused, bool):
        raise SpecError('"schedule.paused" must be true or false.')
    out: Dict[str, Any] = {
        "every": every,
        "hours": None,
        "at": None,
        "weekday": None,
        "paused": paused,
    }
    if every == "hours":
        hours = schedule.get("hours") or 6
        if hours not in SCHEDULE_HOURS:
            raise SpecError(
                '"schedule.hours" must be one of '
                f'{", ".join(str(h) for h in SCHEDULE_HOURS)}.'
            )
        out["hours"] = hours
        return out
    at = schedule.get("at") or "06:00"
    if not isinstance(at, str) or not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", at):
        raise SpecError('"schedule.at" must be a time like "06:00" (24-hour).')
    out["at"] = at
    if every == "week":
        weekday = str(schedule.get("weekday") or "mon").lower()[:3]
        if weekday not in WEEKDAYS:
            raise _unknown('"schedule.weekday"', schedule.get("weekday"), WEEKDAYS)
        out["weekday"] = weekday
    return out


def read_logo(logo: str, base: Union[str, Path, None] = None) -> str:
    """The logo file as a data URI, so the page needs no other file.

    A relative path is looked up from ``base`` (the folder of the spec).
    """
    import base64

    p = Path(logo).expanduser()
    if not p.is_absolute():
        p = Path(base or ".") / p
    if not p.is_file():
        raise SpecError(f"The logo file was not found: {p}.")
    data = p.read_bytes()
    if len(data) > MAX_LOGO_BYTES:
        raise SpecError(
            f"The logo is {len(data) // 1024} KB; use an image under "
            f"{MAX_LOGO_BYTES // 1024} KB."
        )
    kind = LOGO_TYPES[p.suffix.lower()]
    return f"data:{kind};base64,{base64.b64encode(data).decode()}"


def load_spec(path: Union[str, Path]) -> Dict[str, Any]:
    """Read and validate a spec file."""
    p = Path(path)
    try:
        raw = json.loads(p.read_text())
    except FileNotFoundError:
        raise SpecError(f"No app spec at {p}.")
    except json.JSONDecodeError as exc:
        raise SpecError(f"{p.name} is not valid JSON: {exc}.")
    return validate_spec(raw)


def save_spec(spec: Dict[str, Any], path: Union[str, Path]) -> Path:
    """Validate a spec and write it, defaults included, so it is easy to edit."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(validate_spec(spec), indent=1) + "\n")
    return p
