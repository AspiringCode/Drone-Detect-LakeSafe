from __future__ import annotations

import subprocess
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parent
LEGACY_CLIENT = BACKEND_ROOT / "app" / "risk_zones" / "socrata_client.py"
DEMO_LOADER = BACKEND_ROOT / "app" / "risk_zones" / "demo_fixture_data.py"
REVIEWED_CONNECTOR = (
    BACKEND_ROOT / "app" / "risk_zones" / "connectors" / "king_county_swim_beach.py"
)
FORBIDDEN_PRODUCTION_TEXT = (
    "placeholder_incidents",
    "placeholder_depth_contours",
    "placeholder_access_points",
    "app.risk_zones.socrata_client",
)


def _tracked_production_python_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "backend/app/**/*.py"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [
        REPOSITORY_ROOT / path
        for path in result.stdout.splitlines()
        if (REPOSITORY_ROOT / path).is_file()
    ]


def test_legacy_socrata_client_is_removed() -> None:
    assert not LEGACY_CLIENT.exists()


def test_production_python_has_no_placeholder_dataset_or_legacy_import() -> None:
    findings = {
        str(path.relative_to(REPOSITORY_ROOT)): token
        for path in _tracked_production_python_files()
        for token in FORBIDDEN_PRODUCTION_TEXT
        if token in path.read_text(encoding="utf-8")
    }

    assert findings == {}


def test_reviewed_connector_and_demo_loader_are_separate_modules() -> None:
    assert REVIEWED_CONNECTOR.is_file()
    assert DEMO_LOADER.is_file()
    assert REVIEWED_CONNECTOR.parent != DEMO_LOADER.parent
    assert "demo_fixture_data" not in REVIEWED_CONNECTOR.read_text(encoding="utf-8")
