from __future__ import annotations

import logging
import time
import zipfile
from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, Signal, Slot

from tf3_early_start_manager.models import Installation, Resource
from .cache import SCAN_CACHE_SCHEMA_VERSION

LOGGER = logging.getLogger("tf3_early_start_manager")
SCAN_RELEVANT_SUFFIXES = (".lua", ".tl", ".mdl", ".tga", ".png", ".jpg", ".jpeg")
COMPATIBILITY_MOD_ID = "tf3_early_start_compatibility"
SCAN_DOMAINS = (
    "vehicle", "depots", "stations", "warehouses",
    "infrastructure", "buildings", "industries", "assets",
)

class DirectoryInfo:
    def __init__(self, filename: str):
        self.filename = filename
    def is_dir(self) -> bool:
        return False

class DirectoryArchive:
    """Minimal ZipFile-like read-only adapter for loose mod content."""
    def __init__(self, root: Path, files: list[Path] | None = None):
        self.root = root
        self._files = files if files is not None else [p for p in root.rglob("*") if p.is_file()]
    def infolist(self):
        return [DirectoryInfo(p.relative_to(self.root).as_posix()) for p in self._files]
    def read(self, name: str) -> bytes:
        return (self.root / Path(name)).read_bytes()

class ContentScanWorker(QObject):
    progress = Signal(int, int, str, str, int, int, int)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, scanner, installation: Installation, force_rescan: bool = False):
        super().__init__()
        self.scanner = scanner
        self.installation = installation
        self.force_rescan = force_rescan
        self._cancel_event = Event()

    @Slot()
    def cancel(self):
        self._cancel_event.set()

    @Slot()
    def run(self):
        LOGGER.info("CONTENT_SCAN worker started force=%s", self.force_rescan)
        scan_started = time.perf_counter()
        try:
            discovery_started = time.perf_counter()
            jobs: list[tuple[str, Path, str, str, str, str, Path, bool]] = []
            # Vanilla archives.
            for domain in SCAN_DOMAINS:
                root = self.installation.content / domain
                if root.is_dir():
                    nested_archives = sorted(root.rglob("*.zip"))
                else:
                    nested_archives = []
                for zp in nested_archives:
                    if any(x in zp.name.lower() for x in ("backup", "kopie", "_test")):
                        continue
                    jobs.append((domain, zp, "vanilla", "Vanilla", "", "", self.installation.content, False))
                top_level_archive = self.installation.content / f"{domain}.zip"
                if top_level_archive.is_file():
                    jobs.append((domain, top_level_archive, "vanilla", "Vanilla", "", "", self.installation.content, False))
            # Installed local + Mod.IO packages. These are scanned read-only and
            # keep the authors' historical availability values unchanged.
            for source_type, source_name, source_id, source_namespace, mod_root in self.scanner.installed_mod_sources():
                if source_id == COMPATIBILITY_MOD_ID or source_name == COMPATIBILITY_MOD_ID:
                    continue
                content_root = mod_root / "content" if (mod_root / "content").is_dir() else mod_root
                # Loose resources are the normal layout for local and Mod.IO TF3 mods.
                for domain in SCAN_DOMAINS:
                    domain_root = content_root / domain
                    if domain_root.is_dir():
                        jobs.append((domain, domain_root, source_type, source_name, source_id, source_namespace, content_root, True))
                # Also support mods that package resources in ZIP archives.
                for zp in sorted(content_root.rglob("*.zip")):
                    if any(x in zp.name.lower() for x in ("backup", "kopie", "_test")):
                        continue
                    domain = self.scanner.domain_for_mod_archive(zp, content_root)
                    if domain:
                        jobs.append((domain, zp, source_type, source_name, source_id, source_namespace, content_root, False))
            LOGGER.info("PERF source discovery %.3fs jobs=%d", time.perf_counter() - discovery_started, len(jobs))
            cache_load_started = time.perf_counter()
            cache = {} if self.force_rescan else self.scanner.load_scan_cache()
            cached_archives = cache.get("archives", {}) if isinstance(cache, dict) else {}
            LOGGER.info(
                "PERF cache load %.3fs archives=%d force=%s",
                time.perf_counter() - cache_load_started,
                len(cached_archives) if isinstance(cached_archives, dict) else 0,
                self.force_rescan,
            )
            new_cache = {"version": SCAN_CACHE_SCHEMA_VERSION, "tf3Root": str(self.installation.root), "contentLanguage": self.scanner.language, "archives": {}}
            found: list[Resource] = []
            total = len(jobs)
            cache_hits = 0
            rescanned = 0
            source_seconds = {"vanilla": 0.0, "modio": 0.0, "local": 0.0}
            source_jobs = {"vanilla": 0, "modio": 0, "local": 0}
            source_rescans = {"vanilla": 0, "modio": 0, "local": 0}
            signature_seconds = {"modio": 0.0, "local": 0.0}
            signature_files = {"modio": 0, "local": 0}
            for index, (domain, zp, source_type, source_name, source_id, source_namespace, scan_root, is_loose) in enumerate(jobs, start=1):
                job_started = time.perf_counter()
                source_jobs[source_type] = source_jobs.get(source_type, 0) + 1
                if self._cancel_event.is_set():
                    self.cancelled.emit()
                    return
                try:
                    if is_loose:
                        signature_started = time.perf_counter()
                        loose_files = [
                            p for p in zp.rglob("*")
                            if p.name.lower().endswith(SCAN_RELEVANT_SUFFIXES) and p.is_file()
                        ]
                        loose_stats = [p.stat() for p in loose_files]
                        size_value = sum(stat.st_size for stat in loose_stats)
                        mtime_value = max((stat.st_mtime_ns for stat in loose_stats), default=0)
                        signature_elapsed = time.perf_counter() - signature_started
                        signature_seconds[source_type] = signature_seconds.get(source_type, 0.0) + signature_elapsed
                        signature_files[source_type] = signature_files.get(source_type, 0) + len(loose_files)
                        LOGGER.debug("PERF loose signature %.3fs files=%d path=%s", signature_elapsed, len(loose_files), zp)
                    else:
                        stat = zp.stat()
                        size_value = stat.st_size
                        mtime_value = stat.st_mtime_ns
                    rel = f"{source_type}:{source_id}:{'dir' if is_loose else 'zip'}:{zp.resolve()}"
                except OSError:
                    continue
                cached = cached_archives.get(rel) if isinstance(cached_archives, dict) else None
                hit = (
                    not self.force_rescan
                    and isinstance(cached, dict)
                    and cached.get("size") == size_value
                    and cached.get("mtimeNs") == mtime_value
                    and cached.get("domain") == domain
                    and cached.get("sourceType") == source_type
                )
                if hit:
                    resources = self.scanner.resources_from_cache(cached.get("resources", []))
                    cache_hits += 1
                else:
                    resources = []
                    try:
                        if is_loose:
                            archive = DirectoryArchive(zp, loose_files)
                            resources = self.scanner.group_zip_resources(
                                domain, zp, archive, source_type, source_name, source_id, source_namespace, scan_root
                            )
                        else:
                            with zipfile.ZipFile(zp) as archive:
                                resources = self.scanner.group_zip_resources(
                                    domain, zp, archive, source_type, source_name, source_id, source_namespace, scan_root
                                )
                    except (OSError, zipfile.BadZipFile):
                        pass
                    rescanned += 1
                    source_rescans[source_type] = source_rescans.get(source_type, 0) + 1
                found.extend(resources)
                if hit:
                    # Preserve the validated cache entry verbatim. Avoid rebuilding
                    # thousands of dictionaries during a warm incremental scan.
                    new_cache["archives"][rel] = cached
                else:
                    new_cache["archives"][rel] = {
                        "size": size_value, "mtimeNs": mtime_value, "domain": domain,
                        "sourceType": source_type, "sourceName": source_name, "sourceId": source_id, "sourceNamespace": source_namespace,
                        "resources": [self.scanner.resource_to_cache(r) for r in resources],
                    }
                source_seconds[source_type] = source_seconds.get(source_type, 0.0) + (time.perf_counter() - job_started)
                label = f"{source_type}: {source_name} / {zp.name}" if source_type != "vanilla" else zp.name
                self.progress.emit(index, total, domain, label, len(found), cache_hits, rescanned)
            for source_type in ("vanilla", "modio", "local"):
                LOGGER.info(
                    "PERF source %s %.3fs jobs=%d rescanned=%d",
                    source_type,
                    source_seconds.get(source_type, 0.0),
                    source_jobs.get(source_type, 0),
                    source_rescans.get(source_type, 0),
                )
            LOGGER.info(
                "PERF loose signatures %.3fs files=%d modio=%.3fs/%d local=%.3fs/%d",
                sum(signature_seconds.values()),
                sum(signature_files.values()),
                signature_seconds.get("modio", 0.0),
                signature_files.get("modio", 0),
                signature_seconds.get("local", 0.0),
                signature_files.get("local", 0),
            )
            cache_write_started = time.perf_counter()
            self.scanner.save_scan_cache(new_cache)
            LOGGER.info("PERF cache write %.3fs", time.perf_counter() - cache_write_started)
            LOGGER.info(
                "PERF full content scan %.3fs jobs=%d cacheHits=%d rescanned=%d resources=%d",
                time.perf_counter() - scan_started, total, cache_hits, rescanned, len(found),
            )
            self.finished.emit(found)
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
