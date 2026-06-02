"""Session configuration — minimal identity config for a pipeline session."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SessionConfig:
    """
    Identity config passed to ``OpsRiskClient.open_session()``.

    Args:
        name:
            Human-readable label for this session (e.g. ``"rail-may-2025"``).
            Used only for your own reference — it does not affect processing.
    """

    name: str
