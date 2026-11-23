"""The fleet app: a small local web app over one monitor folder.

    amygda-risk app fleet_monitor

It shows the monitor's dashboard live and adds what a file can't do: run now,
add files, and a schedule that can be set, paused and resumed. It listens on
this machine only and needs nothing beyond the SDK.
"""

from amygda_ops_risk_score.app.server import FleetApp
from amygda_ops_risk_score.app.server import serve

__all__ = ["FleetApp", "serve"]
