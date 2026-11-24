from __future__ import annotations

import json
import os
import re
from pathlib import Path

from tf3_early_start_manager.models import Installation

STEAM_APP_ID = "3493540"

class InstallationService:
    def __init__(self, installation: Installation | None = None):
        self.installation = installation

    @staticmethod
    def validate_installation(root: Path) -> Installation | None:
        if (root / "base" / "content" / "gui.zip").is_file() and (root / "base" / "content").is_dir():
            return Installation(root.resolve(), InstallationService.detect_distribution(root))
        return None

    @staticmethod
    def detect_distribution(root: Path) -> str:
        low = str(root).lower().replace("/", "\\")
        if "\\steamapps\\common\\" in low:
            return "Steam"
        if (root / ".egstore").exists():
            return "Epic"
        if any(root.glob("goggame-*.info")) or any(root.glob("goggame-*.ico")):
            return "GOG"
        return "Custom"

    @staticmethod
    def _registry_values(paths: list[tuple[object, str]], value_names: tuple[str, ...]) -> list[Path]:
        if os.name != "nt":
            return []
        try:
            import winreg
        except ImportError:
            return []
        result: list[Path] = []
        access_modes = (winreg.KEY_READ | winreg.KEY_WOW64_64KEY, winreg.KEY_READ | winreg.KEY_WOW64_32KEY)
        for hive, key_path in paths:
            for access in access_modes:
                try:
                    with winreg.OpenKey(hive, key_path, 0, access) as key:
                        for name in value_names:
                            try:
                                value, _ = winreg.QueryValueEx(key, name)
                                if value:
                                    result.append(Path(os.path.expandvars(str(value))).expanduser())
                            except OSError:
                                pass
                except OSError:
                    pass
        return result

    def steam_install_candidates(self) -> list[Path]:
        roots: list[Path] = []
        if os.name == "nt":
            import winreg
            roots += self._registry_values([
                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
            ], ("SteamPath", "InstallPath"))
        roots += [Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Steam"]
        libraries: list[Path] = []
        for root in roots:
            if root not in libraries:
                libraries.append(root)
            vdf = root / "steamapps" / "libraryfolders.vdf"
            try:
                text = vdf.read_text(encoding="utf-8", errors="ignore")
                for value in re.findall(r'"path"\s+"([^"]+)"', text, re.IGNORECASE):
                    candidate = Path(value.replace("\\\\", "\\"))
                    if candidate not in libraries:
                        libraries.append(candidate)
            except OSError:
                pass
        return [lib / "steamapps" / "common" / "Transport Fever 3" for lib in libraries]

    @staticmethod
    def epic_install_candidates() -> list[Path]:
        manifests = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
        result: list[Path] = []
        if manifests.is_dir():
            for item in manifests.glob("*.item"):
                try:
                    data = json.loads(item.read_text(encoding="utf-8-sig"))
                except (OSError, ValueError):
                    continue
                haystack = " ".join(str(data.get(k, "")) for k in ("DisplayName", "AppName", "CatalogItemId")).lower()
                location = str(data.get("InstallLocation", "")).strip()
                if location and "transport fever 3" in haystack:
                    result.append(Path(location))
        return result

    def gog_install_candidates(self) -> list[Path]:
        if os.name != "nt":
            return []
        import winreg
        result: list[Path] = []
        # Classic GOG installers register games below GOG.com\Games\<product id>.
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for access in (winreg.KEY_READ | winreg.KEY_WOW64_64KEY, winreg.KEY_READ | winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(hive, r"SOFTWARE\GOG.com\Games", 0, access) as parent:
                        for index in range(winreg.QueryInfoKey(parent)[0]):
                            try:
                                with winreg.OpenKey(parent, winreg.EnumKey(parent, index)) as key:
                                    title = ""
                                    for field in ("gameName", "title", "name"):
                                        try:
                                            title = str(winreg.QueryValueEx(key, field)[0])
                                            if title:
                                                break
                                        except OSError:
                                            pass
                                    if "transport fever 3" not in title.lower():
                                        continue
                                    for field in ("path", "installPath", "InstallLocation"):
                                        try:
                                            location = str(winreg.QueryValueEx(key, field)[0]).strip()
                                            if location:
                                                result.append(Path(location))
                                                break
                                        except OSError:
                                            pass
                            except OSError:
                                continue
                except OSError:
                    pass
        uninstall_roots = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]
        access_modes = (winreg.KEY_READ | winreg.KEY_WOW64_64KEY, winreg.KEY_READ | winreg.KEY_WOW64_32KEY)
        for hive, base in uninstall_roots:
            for access in access_modes:
                try:
                    with winreg.OpenKey(hive, base, 0, access) as parent:
                        for index in range(winreg.QueryInfoKey(parent)[0]):
                            try:
                                name = winreg.EnumKey(parent, index)
                                with winreg.OpenKey(parent, name) as key:
                                    display = str(winreg.QueryValueEx(key, "DisplayName")[0])
                                    if "transport fever 3" not in display.lower():
                                        continue
                                    location = str(winreg.QueryValueEx(key, "InstallLocation")[0]).strip()
                                    if location:
                                        result.append(Path(location))
                            except OSError:
                                continue
                except OSError:
                    pass
        galaxy = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "GOG.com" / "Galaxy" / "storage"
        if galaxy.is_dir():
            for db in galaxy.rglob("*.json"):
                try:
                    data = json.loads(db.read_text(encoding="utf-8-sig"))
                except (OSError, ValueError):
                    continue
                if isinstance(data, dict) and "transport fever 3" in str(data).lower():
                    for key in ("installationPath", "install_path", "path"):
                        if data.get(key):
                            result.append(Path(str(data[key])))
        return result

    def installation_candidates(self) -> list[Path]:
        candidates = self.steam_install_candidates() + self.epic_install_candidates() + self.gog_install_candidates()
        unique: list[Path] = []
        seen: set[str] = set()
        for candidate in candidates:
            normalized = os.path.normcase(os.path.abspath(str(candidate)))
            if normalized not in seen:
                seen.add(normalized)
                unique.append(candidate)
        return unique

    def steam_root(self) -> Path | None:
        if not self.installation:
            return None
        p = self.installation.root
        for parent in (p, *p.parents):
            if parent.name.lower() == "steamapps":
                return parent.parent
        return None

    def userdata_mods_dir(self) -> Path:
        root = self.steam_root()
        if not root:
            raise RuntimeError("Steam root could not be derived from the TF3 installation path.")
        userdata = root / "userdata"
        candidates: list[Path] = []
        if userdata.is_dir():
            for user in userdata.iterdir():
                local = user / STEAM_APP_ID / "local"
                if local.is_dir():
                    candidates.append(local / "mods")
        if not candidates:
            raise RuntimeError("TF3 Steam userdata/local directory could not be found.")
        existing = [p for p in candidates if p.is_dir()]
        return (existing or candidates)[0]
