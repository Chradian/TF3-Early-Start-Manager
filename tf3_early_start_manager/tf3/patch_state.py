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

    def tf3_executable(self) -> Path | None:
        if not self.installation:
            return None
        preferred = (
            "TransportFever3.exe", "Transport Fever 3.exe", "transportfever3.exe",
        )
        for name in preferred:
            candidate = self.installation.root / name
            if candidate.is_file():
                return candidate
        executables = sorted(self.installation.root.glob("*.exe"), key=lambda x: x.name.lower())
        game_candidates = [x for x in executables if "transport" in x.name.lower() and "fever" in x.name.lower()]
        return (game_candidates or executables or [None])[0]

    @staticmethod
    def windows_file_version(path: Path) -> dict[str, str]:
        if sys.platform != "win32" or not path.is_file():
            return {}
        try:
            size = ctypes.windll.version.GetFileVersionInfoSizeW(str(path), None)
            if not size:
                return {}
            buffer = ctypes.create_string_buffer(size)
            if not ctypes.windll.version.GetFileVersionInfoW(str(path), 0, size, buffer):
                return {}
            value = ctypes.c_void_p()
            length = wintypes.UINT()
            if not ctypes.windll.version.VerQueryValueW(buffer, "\\", ctypes.byref(value), ctypes.byref(length)):
                return {}
            fixed = ctypes.cast(value, ctypes.POINTER(ctypes.c_uint32))
            file_ms, file_ls = fixed[2], fixed[3]
            product_ms, product_ls = fixed[4], fixed[5]
            def dotted(ms: int, ls: int) -> str:
                return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
            return {"fileVersion": dotted(file_ms, file_ls), "productVersion": dotted(product_ms, product_ls)}
        except (AttributeError, OSError, ValueError):
            return {}

    def tf3_build_info(self) -> dict[str, str]:
        """Read TF3 build metadata from the product metadata block in TransportFever3.exe."""
        if self._tf3_build_info_cache is not None:
            return dict(self._tf3_build_info_cache)
        executable = self.tf3_executable()
        if executable is None or not executable.is_file():
            return {}
        try:
            data = executable.read_bytes()
        except OSError:
            return {}

        def result_from_match(match: re.Match[bytes], source: str) -> dict[str, str]:
            build = match.group(1).decode("ascii", errors="ignore")
            result = {
                "build": build,
                "buildType": "release" if b"release" in data.lower() else "",
                "commit": "",
                "identifier": f"transportfever3/64-bit/{build}",
                "source": source,
            }
            LOGGER.info(
                "TF3_BUILD detected build=%s source=%s identifier=%s",
                result["build"], result["source"], result["identifier"],
            )
            self._tf3_build_info_cache = dict(result)
            return result

        # Confirmed by byte probe on TF3 build 40444:
        # transportfever3\0 64-bit\0\0 40444\0
        strict = re.compile(
            rb"transportfever3\x00+64-bit\x00+(\d{4,8})\x00",
            re.IGNORECASE,
        )
        match = strict.search(data)
        if match:
            return result_from_match(match, "product-metadata")

        # Tolerant fallback for small layout changes while keeping strong anchors.
        relaxed = re.compile(
            rb"transportfever3.{0,32}?64-bit.{0,16}?(\d{4,8})\x00",
            re.IGNORECASE | re.DOTALL,
        )
        match = relaxed.search(data)
        if match:
            return result_from_match(match, "product-metadata-relaxed")

        # Last-resort structural fallback: the confirmed product metadata block
        # can contain a few padding bytes between '64-bit' and the build string.
        product_offset = data.lower().find(b"transportfever3")
        if product_offset >= 0:
            window = data[product_offset:product_offset + 256]
            build_match = re.search(rb"(?<!\d)(\d{4,8})\x00", window)
            if build_match:
                candidate = int(build_match.group(1))
                if 10000 <= candidate <= 99999999:
                    return result_from_match(build_match, "product-metadata-window")

        LOGGER.warning(
            "TF3_BUILD product metadata not found in %s size=%d",
            executable, len(data),
        )
        return {}

    def tf3_build_version(self) -> str:
        return self.tf3_build_info().get("build", "")

    def tf3_executable_fingerprint(self) -> dict:
        if self._tf3_executable_fingerprint_cache is not None:
            return dict(self._tf3_executable_fingerprint_cache)
        executable = self.tf3_executable()
        if executable is None:
            return {"path": "", "exists": False}
        stat = executable.stat()
        result = {
            "path": str(executable), "name": executable.name, "exists": True,
            "sha256": self.sha256_file(executable), "size": stat.st_size,
            "mtimeNs": stat.st_mtime_ns,
        }
        result.update(self.windows_file_version(executable))
        build_info = self.tf3_build_info()
        if build_info:
            result["buildInfo"] = build_info
            result["build"] = build_info.get("build", "")
            result["buildType"] = build_info.get("buildType", "")
            result["commit"] = build_info.get("commit", "")
        self._tf3_executable_fingerprint_cache = dict(result)
        return result

    @staticmethod
    def executable_changed(stored: dict, current: dict) -> bool:
        if not stored or not current.get("exists"):
            return False
        return stored.get("sha256") != current.get("sha256")

    @staticmethod
    def sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def patch_state_path(self) -> Path:
        assert self.installation
        return self.installation.root / ".tf3_early_start_patch_state.json"

    def load_patch_state(self) -> dict:
        if not self.installation:
            return {}
        path = self.patch_state_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        except (OSError, json.JSONDecodeError, UnicodeError):
            return {}
        if not isinstance(data, dict):
            return {}
        if data and data.get("format") == 2:
            data["format"] = PATCH_STATE_FORMAT
            data["currentGeneration"] = max(1, int(data.get("currentGeneration", 1)))
            data["history"] = list(data.get("history", []))
            data["migratedFromFormat"] = 2
        data.setdefault("currentGeneration", 0)
        data.setdefault("history", [])
        return data

    @staticmethod
    def patch_state_snapshot(state: dict, reason: str) -> dict:
        keys = (
            "currentGeneration", "managerVersion", "targetYear", "guiTargetResource",
            "originalSha256", "backupSha256", "patchedSha256", "tf3Executable",
            "tf3Build", "installedAtUnix", "revalidatedAtUnix",
        )
        snapshot = {key: state.get(key) for key in keys if key in state}
        snapshot["archivedAtUnix"] = int(time.time())
        snapshot["reason"] = reason
        return snapshot

    def save_patch_state(self, state: dict) -> None:
        state = dict(state)
        state["format"] = PATCH_STATE_FORMAT
        history = state.get("history", [])
        state["history"] = history[-20:] if isinstance(history, list) else []
        path = self.patch_state_path()
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
        temporary.replace(path)
        self.invalidate_health_cache("patch-state-written")

    def archive_patch_generation(self, state: dict, reason: str) -> list[dict]:
        history = list(state.get("history", [])) if isinstance(state.get("history"), list) else []
        if state.get("currentGeneration", 0):
            history.append(self.patch_state_snapshot(state, reason))
        return history[-20:]

    def patch_health(self) -> tuple[str, str]:
        if self._patch_health_cache is not None:
            return self._patch_health_cache
        result = self._compute_patch_health()
        self._patch_health_cache = result
        return result

    def _compute_patch_health(self) -> tuple[str, str]:
        if not self.installation or not self.installation.gui_zip.is_file():
            return "unavailable", "TF3 installation is unavailable."
        state = self.load_patch_state()
        current_gui_hash = self.sha256_file(self.installation.gui_zip)
        gui_state = self.gui_state()
        current_exe = self.tf3_executable_fingerprint()
        if not state:
            if gui_state == "patched":
                return "legacy", "Patch is installed, but no TF3 executable/gui.zip baseline exists yet. Reinstall once to establish verification."
            if gui_state == "vanilla":
                return "vanilla", "Vanilla TF3 start-year configuration is installed."
            return "changed", "TF3 gui.zip has an unknown state."
        if state.get("format") != PATCH_STATE_FORMAT:
            return "legacy", "Patch state format is unsupported. Reinstall once to establish a current baseline."
        exe_changed = self.executable_changed(state.get("tf3Executable", {}), current_exe)
        if current_gui_hash == state.get("patchedSha256") and gui_state == "patched":
            if exe_changed:
                return "exe_changed_patch_intact", "TF3 executable changed, but the recorded patched gui.zip is still intact. Revalidate to register the new game version."
            return "verified", "TF3 executable and patched gui.zip match the recorded fingerprints."
        if current_gui_hash == state.get("originalSha256") and gui_state == "vanilla":
            if exe_changed:
                return "update_vanilla", "TF3 executable changed and gui.zip is Vanilla. The 1850 patch must be rebuilt for the current game version."
            return "vanilla", "TF3 is using the recorded original gui.zip. The 1850 patch is not installed."
        if gui_state == "vanilla":
            return "update_vanilla", "A new Vanilla gui.zip was detected. The previous backup is stale and will be replaced when the 1850 patch is installed."
        return "changed", "TF3 gui.zip changed to an unknown state. Automatic backup replacement is blocked."

    def gui_backup(self) -> Path:
        assert self.installation
        return self.installation.gui_zip.with_name("gui.zip.earlystart_backup")

    def gui_state(self) -> str:
        if not self.installation:
            return "unknown"
        try:
            with zipfile.ZipFile(self.installation.gui_zip) as z:
                data = z.read(GUI_TARGET_RESOURCE)
        except (OSError, KeyError, zipfile.BadZipFile):
            return "unknown"
        if GUI_PATCHED_BYTES in data:
            return "patched"
        if GUI_VANILLA_BYTES in data:
            return "vanilla"
        return "unknown"
