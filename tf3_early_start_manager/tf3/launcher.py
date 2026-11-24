from __future__ import annotations

import os
import sys
from tf3_early_start_manager.models import Installation

STEAM_APP_ID = "3493540"

def start_game(installation: Installation) -> None:
    if sys.platform == "win32":
        os.startfile(f"steam://rungameid/{STEAM_APP_ID}")
        return
    raise RuntimeError("Direct start is currently implemented for Windows/Steam.")
