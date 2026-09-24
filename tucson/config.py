# tucson/config.py
"""Single source of truth: data/world.toml."""
import os, tomllib
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load(path=None):
    with open(path or os.path.join(ROOT, "data", "world.toml"), "rb") as f:
        return tomllib.load(f)
