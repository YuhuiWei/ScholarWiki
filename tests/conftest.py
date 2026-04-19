import pytest
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def sample_nexus_json(fixtures_dir: Path) -> Path:
    return fixtures_dir / "sample_nexus_result.json"
