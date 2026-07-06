# tests/test_install_scripts.py
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INSTALL = REPO / "scripts" / "install.sh"


def _run(cmd, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run(cmd, env=e, capture_output=True, text=True)


def test_install_sh_exists_and_strict_mode():
    assert INSTALL.exists(), "scripts/install.sh 应存在"
    assert os.access(INSTALL, os.X_OK), "install.sh 应可执行"
    assert "set -euo pipefail" in INSTALL.read_text(encoding="utf-8")


def test_install_dryrun_accepts_current_python():
    r = _run(["bash", str(INSTALL)], env={"COAL_INSTALL_DRYRUN": "1"})
    assert r.returncode == 0, r.stderr
    assert "DRYRUN" in r.stdout and ".venv" in r.stdout


def test_install_rejects_old_python(tmp_path):
    fake = tmp_path / "python3"
    fake.write_text(
        '#!/usr/bin/env bash\n'
        'if [ "$1" = "-c" ]; then echo "3.8"; else exit 0; fi\n',
        encoding="utf-8")
    fake.chmod(0o755)
    env = {"PATH": f"{tmp_path}:{os.environ['PATH']}",
           "COAL_INSTALL_DRYRUN": "1"}
    r = _run(["bash", str(INSTALL)], env=env)
    assert r.returncode != 0
    assert "3.9" in r.stderr
