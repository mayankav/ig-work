"""Legacy flags must stop before imports, bootstrap, state writes or requests."""
import ast
from pathlib import Path
import sys

import pytest

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
import build


@pytest.mark.parametrize("flags", [["--generate"], ["--model", "pro"],
    ["--generate", "--model", "flash"], ["--generate", "--model", "empero"],
    ["--generate", "--fresh"], ["--generate", "--bootstrap"],
    ["--generate", "--no-mascot"]])
def test_legacy_flags_fail_before_any_work(monkeypatch, tmp_path, capsys, flags):
    monkeypatch.setattr(sys, "argv", ["build.py", str(tmp_path / "absent.md"), *flags])
    monkeypatch.setattr(build, "bootstrap", lambda: pytest.fail("bootstrap ran"))
    real_import = __import__
    def guarded_import(name, *args, **kwargs):
        if name in {"mascot", "render", "library", "fresh_poses"}:
            pytest.fail("legacy flags reached " + name)
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr("builtins.__import__", guarded_import)
    with pytest.raises(SystemExit) as exc:
        build.main()
    assert exc.value.code == 2
    assert "No request was sent" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_builder_has_no_obsolete_art_import():
    tree = ast.parse(Path(build.__file__).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name != "mascot" for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            assert node.module != "mascot"
