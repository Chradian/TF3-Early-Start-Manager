from __future__ import annotations
from tf3_early_start_manager.version import APP_VERSION

import json
import logging
import os
import re
import shutil
import tempfile
import time
from collections.abc import Iterable
from pathlib import Path

from tf3_early_start_manager.models import Resource

LOGGER = logging.getLogger("tf3_early_start_manager")
LOGGER = logging.getLogger("tf3_early_start_manager")
TARGET_YEAR = 1850
COMPATIBILITY_MOD_ID = "tf3_early_start_compatibility"
WAREHOUSE_ERA_A_OVERRIDES = {
    "warehouse_era_a_bulk.metacon.tl": "BULK",
    "warehouse_era_a_flatbed.metacon.tl": "FLATBED",
    "warehouse_era_a_goods.metacon.tl": "GOODS",
    "warehouse_era_a_liquid.metacon.tl": "LIQUID",
    "warehouse_era_a_universal.metacon.tl": "UNIVERSAL",
}
WAREHOUSE_OVERRIDE_IDS = {
    f"::/warehouses/{filename}": TARGET_YEAR
    for filename in WAREHOUSE_ERA_A_OVERRIDES
}

class CompatibilityInstaller:
    def __init__(self, host):
        self.host = host
    def __getattr__(self, name):
        return getattr(self.host, name)

    def install_generated_mod(self, generated: Path) -> None:
        mods = self.userdata_mods_dir()
        mods.mkdir(parents=True, exist_ok=True)
        target = mods / COMPATIBILITY_MOD_ID
        backup = target.with_name(target.name + ".update_backup")
        if backup.exists():
            shutil.rmtree(backup)
        try:
            if target.exists():
                shutil.copytree(target, backup)
                # Remove only manager-owned paths. This avoids renaming the live
                # mod directory, which can fail on Windows with WinError 5.
                for name in ("content", "_metadata"):
                    owned_dir = target / name
                    if owned_dir.exists():
                        shutil.rmtree(owned_dir)
                for name in ("mod.json", "overrides.json", "early_start_version.json"):
                    owned_file = target / name
                    if owned_file.exists():
                        owned_file.unlink()
            shutil.copytree(generated, target, dirs_exist_ok=True)
        except (OSError, shutil.Error):
            try:
                if target.exists():
                    shutil.rmtree(target)
                if backup.exists():
                    shutil.copytree(backup, target)
            except (OSError, shutil.Error):
                LOGGER.exception("Compatibility mod rollback failed")
            raise
        finally:
            if backup.exists():
                try:
                    shutil.rmtree(backup)
                except OSError:
                    LOGGER.warning("Could not remove update backup: %s", backup)

    def installed_manifest(self) -> dict:
        try:
            path = self.userdata_mods_dir() / COMPATIBILITY_MOD_ID / "overrides.json"
            return json.loads(path.read_text()) if path.is_file() else {}
        except (OSError, RuntimeError, json.JSONDecodeError):
            return {}
