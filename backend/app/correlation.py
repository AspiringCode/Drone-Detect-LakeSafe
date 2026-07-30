"""Request correlation IDs owned by the server boundary."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import Request


REQUEST_ID_HEADER = "X-Request-ID"


def request_id_from_header(value: str | None) -> UUID:
    """Accept only canonical UUID values; never reflect arbitrary header text."""
    if value:
        try:
            candidate = UUID(value)
        except (TypeError, ValueError, AttributeError):
            pass
        else:
            # UUID accepts several non-canonical representations.  Requiring
            # the canonical spelling keeps audit and tracing identifiers stable.
            if str(candidate) == value.lower():
                return candidate
    return uuid4()


def get_request_id(request: Request) -> UUID:
    value = getattr(request.state, "request_id", None)
    if isinstance(value, UUID):
        return value
    request_id = request_id_from_header(request.headers.get(REQUEST_ID_HEADER))
    request.state.request_id = request_id
    return request_id


__all__ = ["REQUEST_ID_HEADER", "get_request_id", "request_id_from_header"]
