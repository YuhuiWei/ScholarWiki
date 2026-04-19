import pytest
from pathlib import Path
import yaml
from scholarwiki.config import Config, load_config

def test_load_defaults_when_file_missing(tmp_path):
    cfg = load_config(tmp_path / "nonexistent.yaml")
    assert cfg.paths.nexus_inbox == Path("./nexus_inbox")
    assert cfg.paths.raw == Path("./raw")
    assert cfg.paths.wiki == Path("./wiki")

def test_load_from_yaml(tmp_path):
    data = {"paths": {"nexus_inbox": "/data/inbox", "raw": "/data/raw", "wiki": "/data/wiki"}}
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml.dump(data))
    cfg = load_config(cfg_file)
    assert cfg.paths.nexus_inbox == Path("/data/inbox")
    assert cfg.paths.raw == Path("/data/raw")

def test_env_var_substitution_in_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("ZOTERO_API_KEY", "secret123")
    data = {"zotero": {"library_id": "999", "library_type": "user", "api_key": "${ZOTERO_API_KEY}"}}
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml.dump(data))
    cfg = load_config(cfg_file)
    assert cfg.zotero.api_key == "secret123"

def test_linking_config_has_synthesis_and_style_model():
    from scholarwiki.config import LinkingConfig
    cfg = LinkingConfig()
    assert cfg.synthesis_model == "gpt-5"
    assert cfg.style_model == "gpt-4.1"
    assert not hasattr(cfg, "model")  # old field removed
