from pathlib import Path


MIGRATIONS = Path(__file__).resolve().parents[3] / "supabase" / "migrations"


def test_phase2_workflow_migrations_keep_reviews_independent_and_history_append_only():
    workflow = (MIGRATIONS / "0008_station_verification_workflows.sql").read_text()
    hardening = (MIGRATIONS / "0010_station_review_self_approval.sql").read_text()

    assert "audit_events_append_only" in workflow
    assert "before update or delete on public.audit_events" in workflow
    assert "request_row.requested_by = p_reviewer_user_id" in hardening
