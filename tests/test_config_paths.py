import importlib
import config


def test_resolve_db_path_default():
    importlib.reload(config)
    assert str(config.resolve_db_path()).endswith("coal_data.db")


def test_resolve_db_path_env_override(monkeypatch, tmp_path):
    target = tmp_path / "custom.db"
    monkeypatch.setenv("COAL_DB_PATH", str(target))
    assert config.resolve_db_path() == target


def test_resolve_runs_dir_default():
    assert config.resolve_runs_dir().name == "runs"


def test_resolve_runs_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("COAL_RUNS_DIR", str(tmp_path / "r"))
    assert config.resolve_runs_dir() == tmp_path / "r"
