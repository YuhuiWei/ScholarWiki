import shutil
import pytest
from pathlib import Path
from typer.testing import CliRunner
from scholarwiki.cli import app

runner = CliRunner()


@pytest.fixture
def project_dir(tmp_path):
    (tmp_path / "nexus_inbox").mkdir()
    (tmp_path / "manual_inbox").mkdir()
    (tmp_path / "raw").mkdir()
    (tmp_path / "wiki").mkdir()
    shutil.copytree(Path("templates"), tmp_path / "templates")
    cfg_text = f"""
paths:
  nexus_inbox: {tmp_path}/nexus_inbox
  manual_inbox: {tmp_path}/manual_inbox
  raw: {tmp_path}/raw
  staging: {tmp_path}/staging
  wiki: {tmp_path}/wiki
"""
    (tmp_path / "config.yaml").write_text(cfg_text)
    return tmp_path


def test_status_empty(project_dir):
    result = runner.invoke(app, ["status", "--config", str(project_dir / "config.yaml")])
    assert result.exit_code == 0
    assert "0" in result.output


def test_queue_empty(project_dir):
    result = runner.invoke(app, ["queue", "--config", str(project_dir / "config.yaml")])
    assert result.exit_code == 0


def test_ingest_runs_without_error(project_dir):
    result = runner.invoke(app, ["ingest", "--config", str(project_dir / "config.yaml")])
    assert result.exit_code == 0
    assert "Ingested" in result.output or "Nothing" in result.output


def test_status_shows_zotero_unsynced(project_dir):
    result = runner.invoke(app, ["status", "--config", str(project_dir / "config.yaml")])
    assert result.exit_code == 0
    assert "Zotero unsynced" in result.output


def test_zotero_sync_no_papers(project_dir):
    result = runner.invoke(app, ["zotero-sync", "--config", str(project_dir / "config.yaml")])
    assert result.exit_code == 0
    assert "synced" in result.output.lower() or "sync" in result.output.lower()


from unittest.mock import AsyncMock, patch, MagicMock
from scholarwiki.extraction.batch import BatchSubmitResult, BatchCollectResult


def test_extract_requires_one_flag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text("")
    from typer.testing import CliRunner
    from scholarwiki.cli import app
    runner = CliRunner()
    result = runner.invoke(app, ["extract"])
    assert result.exit_code != 0


def test_extract_submit_calls_submit_batch(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text("")
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "registry.json").write_text('{"papers": {}, "stats": {}}')

    submit_result = BatchSubmitResult(batch_id="batch_test", paper_ids=[], request_count=0)
    with patch("scholarwiki.cli.submit_batch", new=AsyncMock(return_value=submit_result)):
        from typer.testing import CliRunner
        from scholarwiki.cli import app
        runner = CliRunner()
        result = runner.invoke(app, ["extract", "--submit"])
    assert result.exit_code == 0


def test_extract_status_reports_no_submitted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text("")
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "registry.json").write_text('{"papers": {}, "stats": {}}')
    from typer.testing import CliRunner
    from scholarwiki.cli import app
    runner = CliRunner()
    result = runner.invoke(app, ["extract", "--status"])
    assert result.exit_code == 0
    assert "No submitted" in result.output


# ─── link command tests ────────────────────────────────────────────────────────

from scholarwiki.linking.batch import LinkBatchSubmitResult, LinkBatchCollectResult


def _make_link_config(tmp_path):
    """Write a minimal config.yaml and empty registry, return config path."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(exist_ok=True)
    (raw_dir / "registry.json").write_text('{"papers": {}}')
    cfg_text = f"""
paths:
  nexus_inbox: {tmp_path}/nexus_inbox
  manual_inbox: {tmp_path}/manual_inbox
  raw: {tmp_path}/raw
  staging: {tmp_path}/staging
  wiki: {tmp_path}/wiki
"""
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(cfg_text)
    return cfg_path


def test_link_submit_no_extracted_papers(tmp_path, monkeypatch):
    """link with no extracted papers prints 'No extracted papers to link.'"""
    monkeypatch.chdir(tmp_path)
    cfg_path = _make_link_config(tmp_path)
    result = runner.invoke(app, ["link", "--config", str(cfg_path)])
    assert result.exit_code == 0
    assert "No extracted papers to link." in result.output


def test_link_status_no_batches(tmp_path, monkeypatch):
    """link --status with no batch IDs prints 'No in-progress link batches.'"""
    monkeypatch.chdir(tmp_path)
    cfg_path = _make_link_config(tmp_path)
    result = runner.invoke(app, ["link", "--status", "--config", str(cfg_path)])
    assert result.exit_code == 0
    assert "No in-progress link batches." in result.output


def test_link_collect_no_batches(tmp_path, monkeypatch):
    """link --collect with no linking_batch_ids prints 'No papers with link batches to collect.'"""
    monkeypatch.chdir(tmp_path)
    cfg_path = _make_link_config(tmp_path)
    result = runner.invoke(app, ["link", "--collect", "--config", str(cfg_path)])
    assert result.exit_code == 0
    assert "No papers with link batches to collect." in result.output


def test_link_submit_calls_submit_link_batches(tmp_path, monkeypatch):
    """link with extracted papers calls submit_link_batches and echoes batch IDs."""
    monkeypatch.chdir(tmp_path)
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(exist_ok=True)
    # One extracted paper with no linking_batch_ids
    registry_data = {
        "papers": {
            "abc123": {
                "paper_id": "abc123",
                "title": "Test Paper",
                "source": "manual",
                "extraction_status": "extracted",
                "linking_batch_ids": {},
            }
        }
    }
    import json
    (raw_dir / "registry.json").write_text(json.dumps(registry_data))

    cfg_text = f"""
paths:
  nexus_inbox: {tmp_path}/nexus_inbox
  manual_inbox: {tmp_path}/manual_inbox
  raw: {tmp_path}/raw
  staging: {tmp_path}/staging
  wiki: {tmp_path}/wiki
"""
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(cfg_text)

    submit_result = LinkBatchSubmitResult(
        gpt5_batch_id="batch_a",
        gpt41_batch_id="batch_b",
        concept_count=1,
        pattern_count=0,
        style_count=1,
    )

    with patch("scholarwiki.cli.submit_link_batches", new=AsyncMock(return_value=submit_result)):
        result = runner.invoke(app, ["link", "--config", str(cfg_path)])

    assert result.exit_code == 0
    assert "batch_a" in result.output
    assert "batch_b" in result.output


def test_link_collect_calls_collect_link_batches(tmp_path, monkeypatch):
    """link --collect with linked papers calls collect_link_batches and echoes result."""
    monkeypatch.chdir(tmp_path)
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(exist_ok=True)
    # One paper with linking_batch_ids
    registry_data = {
        "papers": {
            "abc123": {
                "paper_id": "abc123",
                "title": "Test Paper",
                "source": "manual",
                "extraction_status": "extracted",
                "linking_batch_ids": {
                    "gpt5": "batch_a",
                    "gpt41": "batch_b",
                },
            }
        }
    }
    import json
    (raw_dir / "registry.json").write_text(json.dumps(registry_data))

    cfg_text = f"""
paths:
  nexus_inbox: {tmp_path}/nexus_inbox
  manual_inbox: {tmp_path}/manual_inbox
  raw: {tmp_path}/raw
  staging: {tmp_path}/staging
  wiki: {tmp_path}/wiki
"""
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(cfg_text)

    collect_result = LinkBatchCollectResult(linked=1, errors=[])

    with patch("scholarwiki.cli.collect_link_batches", new=AsyncMock(return_value=collect_result)):
        result = runner.invoke(app, ["link", "--collect", "--config", str(cfg_path)])

    assert result.exit_code == 0
    assert "Linked: 1" in result.output
