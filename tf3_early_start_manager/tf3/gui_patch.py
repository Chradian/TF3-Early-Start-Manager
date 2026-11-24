from __future__ import annotations

import binascii
import ctypes
import hashlib
import json
import logging
import re
import shutil
import sys
import time
import zipfile
from ctypes import wintypes
from pathlib import Path

LOGGER = logging.getLogger("tf3_early_start_manager")

GUI_TARGET_RESOURCE = "gui/menu/new_game_react_util.tl"
GUI_VANILLA_BYTES = b"local YearParams = {1900, 2020, 10}"
GUI_PATCHED_BYTES = b"local YearParams = {1850, 2020, 10}"
PATCH_STATE_FORMAT = 3

class PatchService:
    """1850 gui.zip patch state, verification, backup and byte patching."""
    def __init__(self, host):
        self.host = host

    def __getattr__(self, name):
        return getattr(self.host, name)

    @staticmethod
    def find_central(raw: bytearray, name: str) -> int:
        encoded = name.encode()
        pos = 0
        while True:
            pos = raw.find(b"PK\x01\x02", pos)
            if pos < 0:
                raise RuntimeError("Central directory entry not found")
            length = int.from_bytes(raw[pos + 28:pos + 30], "little")
            if bytes(raw[pos + 46:pos + 46 + length]) == encoded:
                return pos
            pos += 4

    def patch_gui(self) -> None:
        self.invalidate_health_cache("patch-gui-start")
        assert self.installation
        state = self.load_patch_state()
        current_exe = self.tf3_executable_fingerprint()
        current_gui_state = self.gui_state()
        current_gui_hash = self.sha256_file(self.installation.gui_zip)
        history = list(state.get("history", [])) if isinstance(state.get("history"), list) else []
        current_generation = int(state.get("currentGeneration", 0) or 0)
        if current_gui_state == "patched":
            if current_gui_hash == state.get("patchedSha256"):
                backup = self.gui_backup()
                expected_backup = state.get("backupSha256")
                if not backup.is_file() or (expected_backup and self.sha256_file(backup) != expected_backup):
                    raise RuntimeError("Patched gui.zip is known, but its Vanilla backup is missing or does not match the recorded hash.")
                state["format"] = PATCH_STATE_FORMAT
                state["tf3Executable"] = current_exe
                state["tf3Build"] = current_exe.get("build") or self.tf3_build_version() or None
                state["tf3BuildInfo"] = current_exe.get("buildInfo", {})
                state["managerVersion"] = APP_VERSION
                state["revalidatedAtUnix"] = int(time.time())
                state["history"] = history
                state["currentGeneration"] = max(1, current_generation)
                state.pop("migratedFromFormat", None)
                self.save_patch_state(state)
                return
            raise RuntimeError("Patched gui.zip has no matching trusted baseline. Revert or verify the installation before continuing.")
        if current_gui_state != "vanilla":
            raise RuntimeError("Unknown gui.zip state. Automatic patching is blocked.")
        original_hash = current_gui_hash
        new_generation_required = (
            current_generation == 0
            or state.get("originalSha256") != original_hash
            or self.executable_changed(state.get("tf3Executable", {}), current_exe)
        )
        if new_generation_required and current_generation:
            history = self.archive_patch_generation(state, "TF3 installation or Vanilla gui.zip changed")
        next_generation = current_generation + 1 if new_generation_required else max(1, current_generation)
        backup = self.gui_backup()
        backup_is_current = (
            backup.is_file()
            and self.sha256_file(backup) == original_hash
            and state.get("format") == PATCH_STATE_FORMAT
            and state.get("originalSha256") == original_hash
            and not self.executable_changed(state.get("tf3Executable", {}), current_exe)
        )
        if not backup_is_current:
            if backup.exists():
                backup.unlink()
                LOGGER.warning("PATCH stale backup removed before creating current-version backup")
            shutil.copy2(self.installation.gui_zip, backup)
        backup_hash = self.sha256_file(backup)
        with zipfile.ZipFile(self.installation.gui_zip) as z:
            info = z.getinfo(GUI_TARGET_RESOURCE)
            old = z.read(GUI_TARGET_RESOURCE)
        if info.compress_type != zipfile.ZIP_STORED:
            raise RuntimeError("GUI target is compressed")
        new = old.replace(GUI_VANILLA_BYTES, GUI_PATCHED_BYTES, 1)
        if len(new) != len(old) or old == new:
            raise RuntimeError("Expected GUI YearParams pattern not found")
        raw = bytearray(self.installation.gui_zip.read_bytes())
        lh = info.header_offset
        nl = int.from_bytes(raw[lh + 26:lh + 28], "little")
        el = int.from_bytes(raw[lh + 28:lh + 30], "little")
        start = lh + 30 + nl + el
        end = start + info.compress_size
        crc = binascii.crc32(new) & 0xFFFFFFFF
        central = self.find_central(raw, GUI_TARGET_RESOURCE)
        raw[start:end] = new
        raw[lh + 14:lh + 18] = crc.to_bytes(4, "little")
        raw[central + 16:central + 20] = crc.to_bytes(4, "little")
        self.installation.gui_zip.write_bytes(raw)
        self.save_patch_state({
            "format": PATCH_STATE_FORMAT,
            "currentGeneration": next_generation,
            "history": history,
            "managerVersion": APP_VERSION,
            "targetYear": TARGET_YEAR,
            "guiTargetResource": GUI_TARGET_RESOURCE,
            "originalSha256": original_hash,
            "backupSha256": backup_hash,
            "patchedSha256": self.sha256_file(self.installation.gui_zip),
            "tf3Executable": current_exe,
            "tf3Build": current_exe.get("build") or self.tf3_build_version() or None,
            "tf3BuildInfo": current_exe.get("buildInfo", {}),
            "installedAtUnix": int(time.time()),
        })
