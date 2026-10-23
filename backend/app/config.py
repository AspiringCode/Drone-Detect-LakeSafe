from __future__ import annotations

import os

LAKE_BBOX = (47.556, -122.104, 47.606, -122.078)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")
SUPABASE_JWT_ISSUER = os.getenv("SUPABASE_JWT_ISSUER")
SUPABASE_JWT_AUDIENCE = os.getenv("SUPABASE_JWT_AUDIENCE")

# ID.me OIDC credentials are consumed exclusively by the FastAPI service.
# Do not use a VITE_ prefix for any of these values.
IDME_CLIENT_ID = os.getenv("IDME_CLIENT_ID")
IDME_CLIENT_SECRET = os.getenv("IDME_CLIENT_SECRET")
IDME_REDIRECT_URI = os.getenv("IDME_REDIRECT_URI")
IDME_ISSUER = os.getenv("IDME_ISSUER", "https://api.id.me/oidc")
IDME_AUDIENCE = os.getenv("IDME_AUDIENCE")
IDME_AUTHORIZATION_ENDPOINT = os.getenv("IDME_AUTHORIZATION_ENDPOINT", "https://api.id.me/oidc/authorize")
IDME_TOKEN_ENDPOINT = os.getenv("IDME_TOKEN_ENDPOINT", "https://api.id.me/oidc/token")
IDME_JWKS_URI = os.getenv("IDME_JWKS_URI", "https://api.id.me/oidc/.well-known/jwks.json")
IDME_USERINFO_ENDPOINT = os.getenv("IDME_USERINFO_ENDPOINT", "https://api.id.me/oidc/userinfo")
VERIFICATION_SESSION_ENCRYPTION_KEY = os.getenv("VERIFICATION_SESSION_ENCRYPTION_KEY")
IDME_PROFILE_SUCCESS_URL = os.getenv("IDME_PROFILE_SUCCESS_URL", "/profile?verification=idme-success")
IDME_PROFILE_FAILURE_URL = os.getenv("IDME_PROFILE_FAILURE_URL", "/profile?verification=idme-failed")

# Reviewed risk connectors are enabled only by a durable database review record.
# Fixtures remain test-only and are never a production fallback for these values.
RISK_CONNECTOR_REFRESH_HOURS = int(os.getenv("RISK_CONNECTOR_REFRESH_HOURS", "24"))
DEVICE_CLOCK_SKEW_SECONDS = int(os.getenv("DEVICE_CLOCK_SKEW_SECONDS", "30"))
REAL_HEARTBEAT_TTL_SECONDS = int(os.getenv("REAL_HEARTBEAT_TTL_SECONDS", "15"))
# "heartbeat" hands commands to drones in their heartbeat replies (devices/live_commands.py) instead of POSTing to a gateway.
REAL_GATEWAY_URL = os.getenv("REAL_GATEWAY_URL")
# Server-only secret-manager reference. Never use a VITE_ prefix.
REAL_GATEWAY_SIGNING_KEY_REF = os.getenv("REAL_GATEWAY_SIGNING_KEY_REF")
# Hosted dashboard origins allowed by CORS, comma-separated exact URLs (no trailing slash).
CORS_ALLOWED_ORIGINS = [origin.strip() for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if origin.strip()]
