"""Transport for service-side repositories shared by FastAPI worker threads."""

import httpx
from supabase import ClientOptions, create_client


def create_server_client(url: str, key: str):
    # Avoid multiplexing concurrent authorization reads over the same HTTP/2
    # socket: the Windows sync transport can poison that connection on a read.
    transport = httpx.Client(http2=False, timeout=10.0, limits=httpx.Limits(max_connections=20, max_keepalive_connections=10))
    try:
        return create_client(url, key, options=ClientOptions(
            httpx_client=transport, auto_refresh_token=False, persist_session=False,
        ))
    except Exception:
        transport.close()
        raise
