from types import SimpleNamespace

from app.lakes.runtime_repository import SupabaseLakeRuntimeRepository


def test_demo_context_uses_direct_station_relationship():
    class Query:
        def select(self, columns):
            # PostgREST also finds indirect station relationships through inventory.
            assert "stations!lakes_station_id_fkey(simulation_only)" in columns
            return self

        def eq(self, *_args): return self
        def maybe_single(self): return self
        def execute(self):
            return SimpleNamespace(data={
                "lake_id": "judge-lake-beaver", "station_id": "demo-station",
                "demo_source_lake_id": "lake-beaver", "stations": {"simulation_only": True},
            })

    repository = SupabaseLakeRuntimeRepository.__new__(SupabaseLakeRuntimeRepository)
    repository._client = SimpleNamespace(table=lambda _table: Query())
    context = repository.runtime_context("judge-lake-beaver")
    assert context["simulation_source_lake_id"] == "lake-beaver"
    assert context["setup_status"] == "ready"
    assert context["cells"] == []
