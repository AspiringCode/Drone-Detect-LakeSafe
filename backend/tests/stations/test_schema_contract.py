from pathlib import Path


MIGRATION = Path(__file__).parents[3] / "supabase/migrations/0008_station_verification_workflows.sql"


def test_phase_2_tables_are_rls_protected():
    text = MIGRATION.read_text().lower()
    for table in ("verification_sessions", "station_request_reviews", "audit_events"):
        assert f"create table public.{table}" in text
        assert f"alter table public.{table} enable row level security" in text
        assert f"alter table public.{table} force row level security" in text
    assert "token_hash" in text
    assert "owner_user_id" not in text


def test_atomic_workflow_rpcs_and_lake_station_ownership_exist():
    text = MIGRATION.read_text().lower()
    for function in ("accept_station_invitation", "review_station_request", "review_station_join_request", "create_station_lake"):
        assert f"function public.{function}" in text
    assert "station_admin" in text
    assert "p_station_id" in text
