"""@suresilly: easy-going tiny-truth posts with a small green donkey."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path(__file__).resolve().parent
ASSETS = PACKAGE / "assets"
POSTS = ROOT / "posts"
STATE = ROOT / "state"
