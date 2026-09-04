"""The held workflow must load the real checks on a fresh runner."""
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts"))
import check_publish_runtime


def test_checks_load_without_network_or_working_directory(tmp_path):
    code = """
import runpy, socket, sys
def forbidden(*args, **kwargs):
    raise AssertionError('Publication startup must not call a service')
socket.create_connection = forbidden
socket.socket.connect = forbidden
runpy.run_path(sys.argv[1], run_name='__main__')
"""
    result = subprocess.run([sys.executable, "-I", "-c", code,
                             str(ROOT / "scripts/check_publish_runtime.py")],
                            cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "nothing was posted" in result.stdout
    assert not list(tmp_path.iterdir())


def test_wrong_dependency_is_refused(monkeypatch):
    monkeypatch.setattr(check_publish_runtime.metadata, "version", lambda _: "0.0.0")
    with pytest.raises(ValueError, match="required"):
        check_publish_runtime.check()


def test_review_installs_dependencies_before_checks_and_reply():
    workflow = (ROOT / ".github/workflows/review.yml").read_text()
    install = workflow.index("run: python -m pip install --quiet -r .agents/skills/suresilly-carousel/requirements.txt")
    check = workflow.index("run: python scripts/check_publish_runtime.py")
    reply = workflow.index("- name: Act on the reply")
    assert install < check < reply
    assert "inputs.decision == 'publish'" in workflow[install:check]
