"""Workflow tests must declare their YAML parser in the CI install manifest."""
from importlib.metadata import version
from pathlib import Path
import re

import pytest


def test_workflow_yaml_parser_is_declared_and_installed():
    requirements = (Path(__file__).resolve().parents[1] / "requirements.txt").read_text()
    pin = re.search(r"(?im)^pyyaml==([^\s#]+)\s*$", requirements)
    assert pin, "Workflow tests need an exact PyYAML pin in CI requirements"
    assert version("PyYAML") == pin.group(1)
    import yaml
    assert yaml.safe_load("jobs:\n  post:\n    steps: []") == {"jobs": {"post": {"steps": []}}}
