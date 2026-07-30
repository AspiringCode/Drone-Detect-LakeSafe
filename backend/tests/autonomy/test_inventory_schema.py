from pathlib import Path


SQL = (Path(__file__).parents[3] / "supabase" / "migrations" / "0018_simulated_inventory_autonomy.sql").read_text()


def test_allowance_trigger_covers_source_and_station_updates():
    assert "before insert or update of source, station_id" in SQL


def test_assignment_commands_require_active_eligible_simulated_inventory():
    assert "apply assignment requires eligible simulated inventory and active assignment" in SQL
    assert "plan_status <> 'active'" in SQL
    assert "inventory_source <> 'simulated'" in SQL


def test_safety_commands_do_not_need_healthy_active_assignment():
    assert "if new.command_type = 'apply_assignment' then" in SQL
    assert "(command_type = 'apply_assignment') = (zone_assignment_id is not null)" in SQL
