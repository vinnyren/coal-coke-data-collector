import config


def test_resolve_db_path_default(monkeypatch):
    # 显式清空 env，使默认分支不受运行环境已导出的变量影响（无人值守场景常见）
    monkeypatch.delenv("COAL_DB_PATH", raising=False)
    assert str(config.resolve_db_path()).endswith("coal_data.db")


def test_resolve_db_path_env_override(monkeypatch, tmp_path):
    target = tmp_path / "custom.db"
    monkeypatch.setenv("COAL_DB_PATH", str(target))
    assert config.resolve_db_path() == target


def test_resolve_runs_dir_default(monkeypatch):
    monkeypatch.delenv("COAL_RUNS_DIR", raising=False)
    assert config.resolve_runs_dir().name == "runs"


def test_resolve_runs_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("COAL_RUNS_DIR", str(tmp_path / "r"))
    assert config.resolve_runs_dir() == tmp_path / "r"


def test_resolve_runs_dir_expands_user(monkeypatch):
    from pathlib import Path
    monkeypatch.setenv("COAL_RUNS_DIR", "~/coal_runs_xyz")
    assert config.resolve_runs_dir() == Path.home() / "coal_runs_xyz"


def test_resolve_db_path_blank_env_falls_back(monkeypatch):
    # 纯空白应视为未设置，回退默认（否则会得到 Path("  ") 这种垃圾路径）
    monkeypatch.setenv("COAL_DB_PATH", "   ")
    assert str(config.resolve_db_path()).endswith("coal_data.db")
