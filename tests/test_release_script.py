# tests/test_release_script.py
import os
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RELEASE = REPO / "scripts" / "release.sh"

CHANGELOG_FIXTURE = """# 变更日志

说明行，不属于任何版本条目。

## [9.9.9.9] - 2026-01-02

测试功能：这是摘要。

### 新增

- 条目 A

## [9.9.8.0] - 2026-01-01

旧版本摘要。

- 旧条目 B
"""


def _run(cmd, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run(cmd, env=e, capture_output=True, text=True)


def _fake_repo(tmp_path, version="9.9.9.9", changelog=CHANGELOG_FIXTURE):
    """按真实仓库布局搭临时仓：scripts/release.sh + VERSION + CHANGELOG.md。"""
    (tmp_path / "scripts").mkdir()
    dst = tmp_path / "scripts" / "release.sh"
    shutil.copy(RELEASE, dst)
    dst.chmod(0o755)
    (tmp_path / "VERSION").write_text(version, encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    return dst


def test_release_sh_exists_and_strict_mode():
    assert RELEASE.exists(), "scripts/release.sh 应存在"
    assert os.access(RELEASE, os.X_OK), "release.sh 应可执行"
    assert "set -euo pipefail" in RELEASE.read_text(encoding="utf-8")


def test_dryrun_prints_tag_and_title_from_changelog(tmp_path):
    script = _fake_repo(tmp_path)
    r = _run(["bash", str(script)], env={"COAL_RELEASE_DRYRUN": "1"})
    assert r.returncode == 0, r.stderr
    assert "tag=v9.9.9.9" in r.stdout
    assert "title=v9.9.9.9 — 测试功能" in r.stdout


def test_dryrun_notes_cover_current_section_only(tmp_path):
    script = _fake_repo(tmp_path)
    r = _run(["bash", str(script)], env={"COAL_RELEASE_DRYRUN": "1"})
    assert r.returncode == 0, r.stderr
    body = r.stdout.split("NOTES_BEGIN")[1].split("NOTES_END")[0]
    assert "条目 A" in body, "发布说明应包含当前版本条目内容"
    assert "旧条目 B" not in body, "发布说明不应混入更早版本的内容"
    assert "说明行" not in body, "发布说明不应包含文件头部说明"


def test_title_without_colon_uses_whole_summary(tmp_path):
    changelog = CHANGELOG_FIXTURE.replace("测试功能：这是摘要。", "纯摘要无冒号。")
    script = _fake_repo(tmp_path, changelog=changelog)
    r = _run(["bash", str(script)], env={"COAL_RELEASE_DRYRUN": "1"})
    assert r.returncode == 0, r.stderr
    assert "title=v9.9.9.9 — 纯摘要无冒号" in r.stdout
    assert "纯摘要无冒号。" not in r.stdout.split("NOTES_BEGIN")[0], "标题应去掉句尾句号"


def test_rejects_bad_version_format(tmp_path):
    script = _fake_repo(tmp_path, version="abc")
    r = _run(["bash", str(script)], env={"COAL_RELEASE_DRYRUN": "1"})
    assert r.returncode != 0
    assert "VERSION" in r.stderr


def test_fails_when_changelog_entry_missing(tmp_path):
    script = _fake_repo(tmp_path, version="1.0.0.0")
    r = _run(["bash", str(script)], env={"COAL_RELEASE_DRYRUN": "1"})
    assert r.returncode != 0
    assert "CHANGELOG" in r.stderr


def test_dryrun_against_real_repo():
    """真实仓库的 VERSION 必须始终有对应 CHANGELOG 条目（发版前置约束）。"""
    r = _run(["bash", str(RELEASE)], env={"COAL_RELEASE_DRYRUN": "1"})
    assert r.returncode == 0, r.stderr
    assert "tag=v" in r.stdout
