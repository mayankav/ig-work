#!/usr/bin/env python3
"""Load publication checks without reading credentials, state or calling a service."""
from importlib import metadata
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / ".agents/skills/suresilly-carousel"
sys.path.insert(0, str(ENGINE / "scripts"))
sys.path.insert(0, str(ROOT / "scripts"))


def check() -> None:
    for line in (ENGINE / "requirements.txt").read_text().splitlines():
        requirement = line.split("#", 1)[0].strip()
        if not requirement:
            continue
        name, expected = requirement.split("==")
        actual = metadata.version(name)
        if actual != expected:
            raise ValueError(f"{name}: installed {actual}; required {expected}")
    import bibliography
    import art_eligibility
    import render_guard
    import post_to_ig
    assert callable(bibliography.require_deck_support)
    assert callable(post_to_ig.check_export)
    art_eligibility.contract()
    render_guard.contract()


if __name__ == "__main__":
    check()
    print("Publication checks loaded. No service was called and nothing was posted.")
