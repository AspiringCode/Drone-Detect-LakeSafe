import httpx

from app.supabase_transport import create_server_client


def test_server_client_uses_bounded_http1_transport_and_preserves_credentials(monkeypatch):
    import app.supabase_transport as transport

    captured = {}
    real_client = httpx.Client
    requests = []

    def client(**kwargs):
        captured.update(kwargs)
        kwargs["transport"] = httpx.MockTransport(lambda request: (requests.append(request), httpx.Response(200, json=[]))[1])
        return real_client(**kwargs)

    monkeypatch.setattr(transport.httpx, "Client", client)
    db = create_server_client("https://project.supabase.co", "server-test-key")
    try:
        assert db.table("profiles").select("user_id").execute().data == []
        assert captured["http2"] is False
        assert captured["timeout"] == 10.0
        assert requests[0].headers["apikey"] == "server-test-key"
        assert requests[0].headers["authorization"] == "Bearer server-test-key"
        assert db.options.auto_refresh_token is False
        assert db.options.persist_session is False
    finally:
        db.options.httpx_client.close()
