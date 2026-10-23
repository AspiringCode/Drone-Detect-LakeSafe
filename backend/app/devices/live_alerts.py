"""Real-drone alerts waiting to be moved into their lake's operational runtime.

app.main drains this on alert reads so device code never imports app.main.
shortcut: in-process memory like live_positions (one uvicorn worker, lost on
restart); persist to operational_alerts if the backend is scaled out.
"""

from __future__ import annotations

from app.models import Alert

_pending: dict[str, list[Alert]] = {}


def record(lake_id: str, alert: Alert) -> None:
    _pending.setdefault(lake_id, []).append(alert)


def drain(lake_id: str) -> list[Alert]:
    return _pending.pop(lake_id, [])
