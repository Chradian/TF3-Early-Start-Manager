"""Runtime paths for source and PyInstaller builds."""
from __future__ import annotations

import sys
from pathlib import Path


def application_root() -> Path:
    """Writable application root: source project or directory containing frozen EXE."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_root() -> Path:
    """Read-only bundled resources: source project or PyInstaller bundle root."""
    if getattr(sys, "frozen", False):
        bundle = getattr(sys, "_MEIPASS", None)
        if bundle:
            return Path(bundle).resolve()
    return application_root()


APP_ROOT = application_root()
RESOURCE_ROOT = resource_root()
