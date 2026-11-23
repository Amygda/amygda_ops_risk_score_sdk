"""Risk monitor: keep scoring new data with a deployed model.

A monitor is a folder on your machine tied to one deployment::

    fleet_monitor/
      monitor.json   deployment, API, bands, fleet name (no API key)
      bundle.zip     the scoring bundle that was deployed (weights, structure)
      history/       the last stretch of raw logs, sent as history next run
      scores/        scores.parquet: one row per asset and period, upserted
      runs/          one folder per run: what was read, scored and flagged
      dashboard/     index.html, rebuilt after every run
      app.json       optional: which tabs, panels and tiles the dashboard shows
      inbox/         drop new files here; `run` picks them up

With ``storage_kind="sqlite"`` the scores, run records and alerts are kept in
one database file, ``monitor.db``, instead of ``scores/``, ``runs/`` and
``alerts/`` (see ``Monitor.set_storage`` to move an existing monitor).

Logs and scores stay in this folder. Each run sends the new logs plus enough
history to the deployment, then merges the returned scores.

Python::

    from amygda_ops_risk_score.monitor import Monitor
    mon = Monitor.init("fleet_monitor", model="complete_model_x.zip",
                       name="fleet-v1", api_key=KEY)
    mon.run("week_01.csv")

Command line: ``amygda-risk`` with ``init``, ``run``, ``score``, ``dashboard``,
``app``, ``service``, ``design``, ``panels``, ``alerts``, ``storage`` or ``status``
(see ``--help``).
"""

from amygda_ops_risk_score.monitor.dashboard import build_dashboard
from amygda_ops_risk_score.monitor.project import Monitor, MonitorError, RunResult
from amygda_ops_risk_score.monitor.spec import catalogue
from amygda_ops_risk_score.monitor.spec import default_spec
from amygda_ops_risk_score.monitor.spec import SpecError
from amygda_ops_risk_score.monitor.spec import validate_spec

__all__ = [
    "Monitor",
    "MonitorError",
    "RunResult",
    "SpecError",
    "build_dashboard",
    "catalogue",
    "default_spec",
    "validate_spec",
]
