"""Shared test doubles for infrastructure that is deliberately fail-closed.

Route tests exercise authorization and workflow behavior without a running
Supabase instance.  Production never uses this in-memory allowance: the
application's limiter always calls the durable service-role RPC.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _allow_durable_rate_limit_in_isolated_tests(monkeypatch):
    from app.rate_limits import RateLimitResult
    import app.rate_limits as limits

    class _AllowingLimiter:
        def claim(self, **_kwargs):
            return RateLimitResult(True, 0)

    monkeypatch.setattr(limits, "get_rate_limit_repository", lambda: _AllowingLimiter())
