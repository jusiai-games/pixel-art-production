"""Compatibility entry point for the bundled pixel art CLI."""

import runpy
import sys
from pathlib import Path


if __name__ == "__main__":
    repo = Path(__file__).resolve().parents[2]
    script = repo / "plugins" / "pixel-art-production" / "scripts" / "pixel-art" / "pixel_art.py"
    sys.path.insert(0, str(script.parent))
    runpy.run_path(str(script), run_name="__main__")
