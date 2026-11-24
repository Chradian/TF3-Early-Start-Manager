from __future__ import annotations

import gettext
import json
import logging
import os
import re
import zipfile
from pathlib import Path

from tf3_early_start_manager.models import Resource
from .sources import mod_namespace

LOGGER = logging.getLogger("tf3_early_start_manager")
SCAN_RELEVANT_SUFFIXES = (".lua", ".tl", ".mdl", ".tga", ".png", ".jpg", ".jpeg")
SCAN_IMAGE_SUFFIXES = (".tga", ".png", ".jpg", ".jpeg")
INTERNAL_YEAR_SENTINEL = 100000
COMPATIBILITY_MOD_ID = "tf3_early_start_compatibility"
EARLY_START_CAR_PRESET = {
    # Required AI road-traffic pool.
    "coach_01": 1850,
    "coach_02": 1850,
    "coach_03": 1850,
    "coach_04": 1870,
    "coach_05": 1870,
    "coach_06": 1870,
    # Historical player vehicles included in the Easy 1850 baseline.
    "american_post_coach": 1850,
    "droshky": 1850,
    "double_horse": 1850,
    "double_horse_cargo": 1850,
}
EARLY_START_CONSTRUCTION_PRESET = {
    "::/depots/rail/rail_depot.con.lua": 1850,
    "::/depots/rail/rail_maint_station.con.lua": 1850,
    "::/depots/road/road_depot/road_depot.con.lua": 1850,
    "::/depots/road/road_maint_station.con.lua": 1850,
    "::/depots/road/tram_depot/tram_depot.con.lua": 1850,
    "::/depots/water/water_depot.con.lua": 1850,
    "::/depots/water/water_maint_station.con.lua": 1850,
    "::/stations/rail/modular_station/modular_station.con.lua": 1850,
    "::/stations/street/modular_street_station/modular_terminal.con.lua": 1850,
}
CONSTRUCTION_BASELINE_YEAR = 1900
INTEGER_CONSTANT_RE = re.compile(r"\b(?:local\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(-?\d+)\b")
TEMPLATE_CALL_RE = re.compile(
    r"\b(?:addTemplate|makeTemplate|makePassengerTemplate|makeCargoTemplate|addPassengerTemplate|addCargoTemplate)\s*\(\s*"
    r"([A-Za-z_][A-Za-z0-9_]*|-?\d+)\s*,\s*([A-Za-z_][A-Za-z0-9_]*|-?\d+)", re.IGNORECASE,
)
SCAN_DOMAINS = (
    "vehicle",
    "depots",
    "stations",
    "warehouses",
    "infrastructure",
    "buildings",
    "industries",
    "assets",
)
RESOURCE_MODIFIERS = {
    ".mdl": ("loadModel", "verified"),
    ".module.lua": ("loadModule", "verified"),
    ".street.lua": ("loadStreet", "documented"),
    ".track.lua": ("loadTrack", "documented"),
    ".bridge.lua": ("loadBridge", "documented"),
    ".tunnel.lua": ("loadTunnel", "documented"),
    ".con.lua": ("loadConstruction", "documented"),
    ".construction.lua": ("loadConstruction", "documented"),
}
AVAILABILITY_RE = re.compile(r"\bavailability\s*=\s*\{", re.IGNORECASE)
YEAR_FROM_RE = re.compile(r"\byearFrom\s*=\s*(-?\d+)", re.IGNORECASE)
YEAR_TO_RE = re.compile(r"\byearTo\s*=\s*(-?\d+)", re.IGNORECASE)
METADATA_CAR_RE = re.compile(r"\bcar\s*=\s*\{", re.IGNORECASE)
CARRIER_RE = re.compile(r'\bcarrier\s*=\s*["\']([A-Z_]+)["\']', re.IGNORECASE)
DESCRIPTION_NAME_RE = re.compile(r'name\s*=\s*_\(\s*"([^"]+)"\s*\)')
DESCRIPTION_TEXT_RE = re.compile(r'description\s*=\s*_\(\s*"([^"]+)"\s*\)')
TRANSPORT_VEHICLE_RE = re.compile(r"\btransportVehicle\s*=\s*\{", re.IGNORECASE)
COMPARTMENTS_RE = re.compile(r"\bcompartments\s*=\s*\{", re.IGNORECASE)
CARGO_TYPE_RE = re.compile(r'["\']([^"\']+\.cargo)["\']', re.IGNORECASE)
CARGO_CLASSES_BLOCK_RE = re.compile(r"\bcargoClassesIncluded\s*=\s*\{([^}]*)\}", re.IGNORECASE | re.DOTALL)
QUOTED_VALUE_RE = re.compile(r'["\']([^"\']+)["\']')
SEAT_PROVIDER_RE = re.compile(r"\bseatProvider\s*=\s*\{", re.IGNORECASE)
SEATS_RE = re.compile(r"\bseats\s*=\s*\{", re.IGNORECASE)
LAND_VEHICLE_RE = re.compile(r"\blandVehicle\s*=\s*\{", re.IGNORECASE)
ENGINES_RE = re.compile(r"\bengines\s*=\s*\{", re.IGNORECASE)
ENGINE_TYPE_RE = re.compile(r'\btype\s*=\s*["\'](STEAM|DIESEL|ELECTRIC)["\']', re.IGNORECASE)
PASSENGER_CARGO_SUFFIX = "/cargos/passengers/passengers.cargo"


class ScannerService:
    """Scanner domain service. UI state is accessed only through the host adapter."""
    def __init__(self, host):
        self.host = host

    def __getattr__(self, name):
        return getattr(self.host, name)

    def installed_mod_sources(self) -> list[tuple[str, str, str, str, Path]]:
        """Return installed mod roots as (type, display name, id, path).

        TF3 local mods live in Steam userdata/<user>/3493540/local/mods.
        Mod.IO installs are stored system-wide below the Public Mod.IO game directory.
        Both sources are scanned read-only.
        """
        sources: list[tuple[str, str, str, str, Path]] = []
        seen: set[Path] = set()

        # Local, manually installed TF3 mods.
        try:
            local_root = self.userdata_mods_dir()
        except RuntimeError:
            local_root = None
        if local_root and local_root.is_dir():
            for mod_dir in sorted((p for p in local_root.iterdir() if p.is_dir()), key=lambda p: p.name.lower()):
                if mod_dir.name == COMPATIBILITY_MOD_ID:
                    continue
                if not (mod_dir / "content").is_dir() and not (mod_dir / "mod.json").is_file():
                    continue
                resolved = mod_dir.resolve()
                seen.add(resolved)
                display_name = self.mod_display_name(mod_dir)
                LOGGER.info("SOURCE_DISCOVERY LOCAL id=%s path=%s name=%s", mod_dir.name, mod_dir, display_name)
                sources.append(("local", display_name, mod_dir.name, self.mod_namespace(mod_dir), mod_dir))

        # TF3 Mod.IO storage. 10640 is the Mod.IO game container used by TF3.
        public_root = Path(os.environ.get("PUBLIC", r"C:\Users\Public"))
        modio_root = public_root / "mod.io" / "10640" / "mods"
        if modio_root.is_dir():
            for mod_dir in sorted((p for p in modio_root.iterdir() if p.is_dir()), key=lambda p: p.name.lower()):
                if mod_dir.resolve() in seen:
                    continue
                if not (mod_dir / "content").is_dir() and not (mod_dir / "mod.json").is_file():
                    continue
                resolved = mod_dir.resolve()
                seen.add(resolved)
                display_name = self.mod_display_name(mod_dir)
                LOGGER.info("SOURCE_DISCOVERY MODIO id=%s path=%s name=%s", mod_dir.name, mod_dir, display_name)
                sources.append(("modio", display_name, mod_dir.name, self.mod_namespace(mod_dir), mod_dir))

        return sources

    @staticmethod
    def mod_namespace(mod_root: Path) -> str:
        return mod_namespace(mod_root)

    def mod_display_name(self, mod_root: Path) -> str:
        for candidate in (mod_root / "_metadata" / "modinfo.json", mod_root / "modinfo.json", mod_root / "mod.json"):
            if not candidate.is_file():
                continue
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, UnicodeError):
                continue
            for key in ("name", "displayName", "title"):
                text = self.localized_content(data.get(key), identifier=mod_root.name)
                if text and text != mod_root.name:
                    return text
        return mod_root.name

    def mod_description(self, scan_root: Path | None, source_type: str) -> str:
        if source_type == "vanilla":
            return self.tr("content.vanilla_description")
        if scan_root is None:
            return self.tr("content.no_description")
        root = scan_root.parent if scan_root.name.lower() == "content" else scan_root
        candidates = (
            root / "_metadata" / "modinfo.json",
            root / "modinfo.json",
            root / "mod.json",
        )
        for candidate in candidates:
            if not candidate.is_file():
                continue
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, UnicodeError):
                continue
            for key in ("description", "summary"):
                value = data.get(key)
                text = self.localized_content(value)
                if text:
                    return re.sub(r"<[^>]+>", "", text).strip()
        return self.tr("content.no_description")

    @staticmethod
    def domain_for_mod_archive(zip_path: Path, mod_root: Path) -> str | None:
        parts = [part.lower() for part in zip_path.parts]
        for domain in SCAN_DOMAINS:
            if domain in parts:
                return domain
        stem = zip_path.stem.lower()
        aliases = {"vehicles": "vehicle", "roads": "infrastructure", "tracks": "infrastructure"}
        if stem in SCAN_DOMAINS:
            return stem
        return aliases.get(stem)

    @staticmethod
    def _cheap_path_marker(path: Path) -> dict:
        try:
            stat = path.stat()
        except OSError:
            return {"exists": False}
        return {
            "exists": True,
            "size": stat.st_size if path.is_file() else 0,
            "mtimeNs": stat.st_mtime_ns,
        }

    def cheap_source_snapshot(self) -> dict:
        """Build a sub-second source inventory without opening archives or walking content trees."""
        snapshot: dict[str, object] = {
            "tf3Root": str(self.installation.root) if self.installation else "",
            "vanilla": {},
            "modio": {},
            "local": {},
        }
        if self.installation:
            vanilla: dict[str, dict] = {}
            marker_paths = [self.installation.gui_zip]
            marker_paths.extend(self.installation.content / f"{domain}.zip" for domain in SCAN_DOMAINS)
            for marker in marker_paths:
                vanilla[str(marker.relative_to(self.installation.root)).replace("\\", "/")] = self._cheap_path_marker(marker)
            snapshot["vanilla"] = vanilla
        for source_type, _source_name, source_id, _source_namespace, mod_root in self.installed_mod_sources():
            source_rows = snapshot[source_type]
            if not isinstance(source_rows, dict):
                continue
            markers = {
                "root": self._cheap_path_marker(mod_root),
                "content": self._cheap_path_marker(mod_root / "content"),
            }
            for filename in ("mod.json", "modinfo.json", "_metadata/modinfo.json"):
                candidate = mod_root / Path(filename)
                if candidate.exists():
                    markers[filename] = self._cheap_path_marker(candidate)
            source_rows[source_id] = markers
        return snapshot

    def translated_resource_name(self, text: str, internal_path: str) -> str:
        name_match = DESCRIPTION_NAME_RE.search(text)
        if name_match:
            key = name_match.group(1)
            translated = self.tf3_translations.gettext(key)
            if translated and translated != key:
                return translated
            readable = key.removeprefix("VEHICLE_").replace("_NAME", "").replace("_", " ").title()
            if readable and readable != key:
                return readable
            return self.localized_content({}, raw=key, identifier=Path(internal_path).stem)
        return self.localized_content({}, identifier=Path(internal_path).stem)

    def mod_string_catalog(self, scan_root: Path | None) -> dict:
        if scan_root is None: return {}
        root = scan_root.parent if scan_root.name.lower() == "content" else scan_root
        for candidate in (root / "strings.json", root / "_metadata" / "strings.json"):
            if candidate.is_file():
                try:
                    data = json.loads(candidate.read_text(encoding="utf-8"))
                    if isinstance(data, dict): return data
                except (OSError, json.JSONDecodeError, UnicodeError): pass
        return {}

    def translated_mod_string(self, catalog: dict, key: str) -> str:
        return self.i18n.catalog_value(catalog, key, identifier=key)

    @staticmethod
    def decode(data: bytes) -> str | None:
        for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                pass
        return None

    @staticmethod
    def extension(path: str) -> str:
        low = path.lower()
        for ext in (".construction.lua", ".module.lua", ".street.lua", ".track.lua", ".bridge.lua", ".tunnel.lua", ".con.lua", ".mdl"):
            if low.endswith(ext):
                return ext
        return Path(low).suffix

    @staticmethod
    def brace_block(text: str, start: int) -> str | None:
        opening = text.find("{", start)
        if opening < 0:
            return None
        depth = 0
        string = None
        escaped = False
        for i in range(opening, len(text)):
            c = text[i]
            if string:
                if escaped:
                    escaped = False
                elif c == "\\":
                    escaped = True
                elif c == string:
                    string = None
                continue
            if c in ('"', "'"):
                string = c
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return text[opening:i + 1]
        return None

    def resource_id(self, domain: str, zip_path: Path, internal: str, scan_root: Path | None = None) -> str:
        assert self.installation
        root = scan_root or self.installation.content
        try:
            relative = zip_path.relative_to(root)
            prefix = "/".join(relative.parts if zip_path.is_dir() else relative.parts[:-1])
        except ValueError:
            prefix = domain
        clean = internal.replace(chr(92), "/").lstrip("/")
        return f"::/{prefix}/{clean}" if prefix else f"::/{clean}"

    @staticmethod
    def logical_basename(internal_path: str) -> str:
        name = Path(internal_path).name
        low = name.lower()
        suffixes = (
            ".construction.lua", ".street_template.lua", ".module.lua",
            ".street.lua", ".track.lua", ".bridge.lua", ".tunnel.lua",
            ".con.lua", ".gtex.lua", ".script.lua", ".mdl", ".tl",
            "_preview@2x.tga", "_preview.tga", "@2x.tga", ".tga",
        )
        for suffix in suffixes:
            if low.endswith(suffix):
                return name[: len(name) - len(suffix)]
        return Path(name).stem

    @staticmethod
    def best_preview_file(
        base: str,
        files: list[str],
        lookup: dict[str, str] | None = None,
        image_files: list[str] | None = None,
    ) -> str | None:
        if lookup is None:
            lookup = {Path(file).name.lower(): file for file in files}
        candidates = (
            f"{base}_preview@2x.tga", f"{base}_preview.tga",
            f"{base}@2x.tga", f"{base}.tga",
            f"{base}_preview.png", f"{base}.png",
            f"{base}_preview.jpg", f"{base}.jpg",
            f"{base}_preview.jpeg", f"{base}.jpeg",
        )
        for candidate in candidates:
            if candidate.lower() in lookup:
                return lookup[candidate.lower()]

        if image_files is None:
            image_files = [
                file for file in files
                if Path(file).suffix.lower() in {".tga", ".png", ".jpg", ".jpeg"}
            ]
        # TF3 commonly uses *preview@2x.tga. Prefer any preview tied to the
        # logical basename before falling back to a normal @2x icon.
        ranked = sorted(
            image_files,
            key=lambda file: (
                0 if "preview@2x" in Path(file).name.lower() else
                1 if "preview" in Path(file).name.lower() else
                2 if "@2x" in Path(file).name.lower() else 3,
                0 if base.lower() in Path(file).name.lower() else 1,
                Path(file).name.lower(),
            ),
        )
        return ranked[0] if ranked else None

    @staticmethod
    def primary_group_file(base: str, files: list[str]) -> str:
        priorities = (
            f"{base}.con.lua", f"{base}.construction.lua", f"{base}.module.lua",
            f"{base}.street.lua", f"{base}.track.lua", f"{base}.bridge.lua",
            f"{base}.tunnel.lua", f"{base}.mdl",
        )
        by_name = {Path(file).name.lower(): file for file in files}
        for candidate in priorities:
            if candidate.lower() in by_name:
                return by_name[candidate.lower()]
        return files[0]

    @staticmethod
    def construction_template_timeline(text: str) -> tuple[tuple[int, int], ...]:
        constants = {m.group(1): int(m.group(2)) for m in INTEGER_CONSTANT_RE.finditer(text)}
        timeline: list[tuple[int, int]] = []
        for match in TEMPLATE_CALL_RE.finditer(text):
            values = []
            for raw in (match.group(1), match.group(2)):
                try:
                    values.append(int(raw))
                except ValueError:
                    values.append(constants.get(raw))
            if None not in values:
                pair = (int(values[0]), int(values[1]))
                if pair not in timeline:
                    timeline.append(pair)
        return tuple(timeline)

    @staticmethod
    def effective_template_year(timeline: tuple[tuple[int, int], ...]) -> int | None:
        years = [start for start, _ in timeline if 0 < start < INTERNAL_YEAR_SENTINEL]
        return min(years) if years else None

    @staticmethod
    def metadata_block(text: str) -> str:
        position = text.find("metadata =")
        return ScannerService.brace_block(text, position) or "" if position >= 0 else ""

    @staticmethod
    def semantic_vehicle_category(
        resource_id: str,
        zip_path: Path,
        internal_path: str,
        scan_root: Path | None,
        metadata_car: bool,
        carrier: str,
    ) -> str:
        known = {
            "plane": "Air", "aircraft": "Air", "helicopter": "Air", "heli": "Air",
            "air": "Air", "zeppelin": "Air", "aw109": "Air", "zmc2": "Air",
            "train": "Rail", "rail": "Rail", "waggon": "Rail",
            "wagon": "Rail", "bus": "Road", "truck": "Road", "road": "Road",
            "tram": "Tram", "ship": "Water", "water": "Water", "car": "AI Traffic",
        }
        candidates: list[str] = []
        def add_parts(value: str) -> None:
            candidates.extend(part for part in value.lower().replace("\\", "/").split("/") if part)
        add_parts(resource_id)
        add_parts(internal_path)
        if scan_root is not None:
            try:
                relative = zip_path.relative_to(scan_root)
                candidates.extend(part.lower() for part in relative.parts)
            except ValueError:
                pass
        candidates.extend(part.lower() for part in zip_path.parts)
        candidates.append(zip_path.stem.lower())
        # Prefer the explicit segment immediately following vehicle.
        for sequence in (resource_id, internal_path):
            parts = [part for part in sequence.lower().replace("\\", "/").split("/") if part]
            if "vehicle" in parts:
                index = parts.index("vehicle")
                if index + 1 < len(parts) and parts[index + 1] in known:
                    return known[parts[index + 1]]
        for candidate in candidates:
            if candidate in known:
                return known[candidate]
        # Unknown mod folders fall back to the actual transport carrier.
        carrier_categories = {"AIR": "Air", "RAIL": "Rail", "ROAD": "Road", "TRAM": "Tram", "WATER": "Water"}
        if carrier in carrier_categories:
            return carrier_categories[carrier]
        if metadata_car:
            return "AI Traffic"
        return "Other"

    @staticmethod
    def is_support_resource(path: str) -> bool:
        low=path.lower().replace("\\","/"); stem=Path(low).stem.split(".")[0]
        return Path(low).suffix.lower() in {".tga",".png",".jpg",".jpeg"} or stem.startswith("menu_") or "/menu/" in low or "/icons/" in low or "_icon" in stem or "preview" in stem or "@2x" in stem

    def group_zip_resources(
        self, domain: str, zip_path: Path, archive: zipfile.ZipFile,
        source_type: str = "vanilla", source_name: str = "Vanilla", source_id: str = "",
        source_namespace: str = "", scan_root: Path | None = None,
    ) -> list[Resource]:
        """Build logical game-object resources instead of exposing each support file."""
        files = [
            info.filename for info in archive.infolist()
            if not info.is_dir() and info.filename.lower().endswith(SCAN_RELEVANT_SUFFIXES)
        ]
        archive_images = [f for f in files if f.lower().endswith(SCAN_IMAGE_SUFFIXES)]
        archive_lookup = {Path(f).name.lower(): f for f in archive_images}
        grouped: dict[str, list[str]] = {}
        for file in files:
            base = self.logical_basename(file)
            # Group by directory + logical basename to avoid collisions.
            parent = str(Path(file).parent).replace("\\", "/")
            key = f"{parent}/{base}" if parent not in (".", "") else base
            grouped.setdefault(key, []).append(file)

        result: list[Resource] = []
        string_catalog = self.mod_string_catalog(scan_root) if source_type != "vanilla" else {}
        for key, group_files in grouped.items():
            base = key.rsplit("/", 1)[-1]
            primary = self.primary_group_file(base, group_files)
            if self.is_support_resource(primary): continue
            preview = self.best_preview_file(base, group_files)
            if preview is None:
                preview = self.best_preview_file(base, files, archive_lookup, archive_images)

            # Only game-object groups with a known primary resource are shown.
            ext = self.extension(primary)
            mod, confidence = RESOURCE_MODIFIERS.get(ext, (None, "analysis"))
            if mod is None:
                con=next((f for f in group_files if f.lower().endswith((".con.lua",".construction.lua"))),None)
                if con is None: continue
                primary=con; ext=self.extension(primary); mod,confidence=RESOURCE_MODIFIERS.get(ext,(None,"analysis"))
                if mod is None: continue

            year_from = 0
            year_to = 0
            metadata_car = False
            carrier = ""
            vehicle_role = ""
            power_type = ""
            display_name = base
            resource_description = ""
            availability_found = False
            template_timeline: tuple[tuple[int, int], ...] = ()
            parsed_texts: list[str] = []

            # Availability/name may be on the primary or one of its supporting files.
            for candidate in [primary, *[f for f in group_files if f != primary]]:
                if not candidate.lower().endswith((".lua", ".tl", ".mdl")):
                    continue
                try:
                    text = self.decode(archive.read(candidate))
                except (KeyError, OSError, zipfile.BadZipFile):
                    continue
                if not text:
                    continue
                parsed_texts.append(text)
                if candidate == primary and ext in {".con.lua", ".construction.lua"}:
                    template_timeline = self.construction_template_timeline(text)
                translated = self.translated_resource_name(text, candidate)
                name_match = DESCRIPTION_NAME_RE.search(text)
                description_match = DESCRIPTION_TEXT_RE.search(text)
                if source_type != "vanilla":
                    if name_match:
                        translated = self.translated_mod_string(string_catalog, name_match.group(1)) or translated
                    if description_match and not resource_description:
                        resource_description = self.translated_mod_string(string_catalog, description_match.group(1))
                elif description_match and not resource_description:
                    description_key = description_match.group(1)
                    localized_description = self.tf3_translations.gettext(description_key)
                    if localized_description and localized_description != description_key:
                        resource_description = localized_description.strip()
                    else:
                        resource_description = self.localized_content({}, raw=description_key, identifier=base)
                if translated != Path(candidate).stem:
                    display_name = translated
                metadata_pos = text.find("metadata =")
                if metadata_pos >= 0:
                    metadata_text = text[metadata_pos:]
                    if METADATA_CAR_RE.search(metadata_text):
                        metadata_car = True
                    if not carrier:
                        carrier_match = CARRIER_RE.search(metadata_text)
                        if carrier_match:
                            carrier = carrier_match.group(1).upper()
                if not availability_found:
                    match = AVAILABILITY_RE.search(text)
                    if match:
                        block = self.brace_block(text, match.start())
                        if block:
                            fm, tm = YEAR_FROM_RE.search(block), YEAR_TO_RE.search(block)
                            if fm or tm:
                                year_from = int(fm.group(1)) if fm else 0
                                year_to = int(tm.group(1)) if tm else 0
                                availability_found = True

            # Include constructions even without direct availability: these are
            # essential for diagnosing missing 1850 depots/stations.
            if not availability_found and mod is None:
                # infer primary construction type from .con.lua where available
                con = next((f for f in group_files if f.lower().endswith(".con.lua")), None)
                if con:
                    primary = con
                    ext = ".con.lua"
                    mod, confidence = RESOURCE_MODIFIERS[ext]
                else:
                    continue

            if domain == "vehicle" and ext == ".mdl":
                try:
                    primary_text = self.decode(archive.read(primary)) or ""
                except (KeyError, OSError, zipfile.BadZipFile):
                    primary_text = ""
                metadata_text = self.metadata_block(primary_text)
                if not TRANSPORT_VEHICLE_RE.search(metadata_text):
                    vehicle_role = "support"
                else:
                    cargo_types = {
                        match.group(1).replace("\\", "/").lower()
                        for match in CARGO_TYPE_RE.finditer(metadata_text)
                    }
                    cargo_classes: set[str] = set()
                    for class_block in CARGO_CLASSES_BLOCK_RE.finditer(metadata_text):
                        cargo_classes.update(
                            value.upper()
                            for value in QUOTED_VALUE_RE.findall(class_block.group(1))
                        )
                    passenger_definition = (
                        any(cargo.endswith(PASSENGER_CARGO_SUFFIX) for cargo in cargo_types)
                        or "PASSENGERS" in cargo_classes
                    )
                    cargo_definition = (
                        any(not cargo.endswith(PASSENGER_CARGO_SUFFIX) for cargo in cargo_types)
                        or bool(cargo_classes - {"PASSENGERS"})
                    )
                    seat_provider = SEAT_PROVIDER_RE.search(metadata_text)
                    has_real_passenger_seats = False
                    if seat_provider:
                        seat_block = self.brace_block(metadata_text, seat_provider.start()) or ""
                        seats_match = SEATS_RE.search(seat_block)
                        if seats_match:
                            seats_block = self.brace_block(seat_block, seats_match.start()) or ""
                            has_real_passenger_seats = bool(re.search(r"\banimation\s*=|\btransf\s*=", seats_block))
                    if cargo_definition:
                        vehicle_role = "cargo"
                    elif passenger_definition and has_real_passenger_seats:
                        vehicle_role = "passenger"
                    elif passenger_definition:
                        # Some car-transport wagons use PASSENGERS as a technical
                        # transport class but contain no actual passenger seats.
                        vehicle_role = "primary"
                    elif not COMPARTMENTS_RE.search(metadata_text):
                        vehicle_role = "group"
                    else:
                        vehicle_role = "primary"
                    land_vehicle_match = LAND_VEHICLE_RE.search(metadata_text)
                    engine_types: set[str] = set()
                    if land_vehicle_match:
                        land_vehicle_block = self.brace_block(metadata_text, land_vehicle_match.start()) or ""
                        engines_match = ENGINES_RE.search(land_vehicle_block)
                        if engines_match:
                            engines_block = self.brace_block(land_vehicle_block, engines_match.start()) or ""
                            engine_types = {
                                match.group(1).upper()
                                for match in ENGINE_TYPE_RE.finditer(engines_block)
                            }
                    if engine_types == {"STEAM"}:
                        power_type = "steam"
                    elif engine_types == {"DIESEL"}:
                        power_type = "diesel"
                    elif engine_types == {"ELECTRIC"}:
                        power_type = "electric"
                    else:
                        power_type = "other"
            category_root = ((scan_root or self.installation.content) / domain) if self.installation else zip_path.parent
            if zip_path.is_dir():
                parent = Path(primary).parent
                category = parent.parts[0] if parent.parts and parent.parts[0] not in (".", domain) else domain
            else:
                category = zip_path.parent.name if zip_path.parent != category_root else zip_path.stem
            rid = self.resource_id(domain, zip_path, primary, scan_root)
            if domain == "vehicle":
                category = self.semantic_vehicle_category(rid, zip_path, primary, scan_root, metadata_car, carrier)
                if not availability_found or year_from <= 1:
                    LOGGER.debug("SKIP vehicle without usable timeline %s yearFrom=%s", primary, year_from)
                    continue
            effective_template_start = self.effective_template_year(template_timeline)
            template_based = effective_template_start is not None
            if template_based:
                year_from = effective_template_start
                year_to = 0 if any(end == 0 for _, end in template_timeline) else max(end for _, end in template_timeline)
            vid = Path(primary).stem.split(".")[0]
            car_locked = source_type == "vanilla" and domain == "vehicle" and vid in EARLY_START_CAR_PRESET and metadata_car
            construction_locked = source_type == "vanilla" and rid in EARLY_START_CONSTRUCTION_PRESET and effective_template_start == CONSTRUCTION_BASELINE_YEAR
            locked = car_locked or construction_locked
            new_year = (EARLY_START_CAR_PRESET[vid] if car_locked else
                        EARLY_START_CONSTRUCTION_PRESET[rid] if construction_locked else year_from)
            description = resource_description or self.mod_description(scan_root, source_type)
            result.append(Resource(
                display_name, rid, domain, category, ext, mod, confidence,
                zip_path, primary, year_from, year_to, new_year, year_to,
                metadata_car, carrier, locked, key, primary, tuple(sorted(group_files)), preview,
                year_from >= INTERNAL_YEAR_SENTINEL, template_timeline, template_based,
                source_type, source_name, source_id, vehicle_role, power_type, description, source_namespace,
            ))
        return result
