from __future__ import annotations

from tf3_early_start_manager.version import APP_NAME, APP_VERSION


import binascii
import ctypes
import gettext
import hashlib
import json
import logging
import logging.handlers
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from collections.abc import Iterable
from ctypes import wintypes
from pathlib import Path

from tf3_early_start_manager.paths import APP_ROOT, RESOURCE_ROOT

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QSettings,
    QSortFilterProxyModel,
    Qt,
    QThread,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QAction, QColor, QGuiApplication, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplashScreen,
    QSplitter,
    QStackedWidget,
    QTableView,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

LOG_DIR = APP_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "tf3_early_start_manager.log"
LOGGER = logging.getLogger("tf3_early_start_manager")
LOGGER.setLevel(logging.DEBUG)
if not LOGGER.handlers:
    _handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.addHandler(_handler)

# Cache schema is independent from the app version. Bump only when the
# cached resource data model changes.

SCAN_RELEVANT_SUFFIXES = (".lua", ".tl", ".mdl", ".tga", ".png", ".jpg", ".jpeg")
SCAN_IMAGE_SUFFIXES = (".tga", ".png", ".jpg", ".jpeg")
STEAM_APP_ID = "3493540"
TARGET_YEAR = 1850
REFERENCE_YEAR = 1900
INTERNAL_YEAR_SENTINEL = 100000

GUI_TARGET_RESOURCE = "gui/menu/new_game_react_util.tl"
GUI_VANILLA_BYTES = b"local YearParams = {1900, 2020, 10}"
GUI_PATCHED_BYTES = b"local YearParams = {1850, 2020, 10}"
COMPATIBILITY_MOD_ID = "tf3_early_start_compatibility"
PATCH_STATE_FORMAT = 3

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

# Documented TF resource modifier classes. loadModel is additionally verified
# by the Early Start 1850 coach test.
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


from tf3_early_start_manager.models import Installation, Resource
from tf3_early_start_manager.ui import ResourceFilterProxyModel, ResourceTableModel
from tf3_early_start_manager.ui.easy_mode import EasyModeBuilder
from tf3_early_start_manager.ui.advanced_mode import AdvancedModeBuilder
from tf3_early_start_manager.ui.header import HeaderController
from tf3_early_start_manager.ui.settings_dialog import SettingsDialogController
from tf3_early_start_manager.ui.resource_tree import ResourceTreeController
from tf3_early_start_manager.ui.resource_preview import ResourcePreviewController
from tf3_early_start_manager.ui.resource_controller import ResourceSelectionController
from tf3_early_start_manager.compatibility import CompatibilityAnalyzer, CompatibilityGenerator, CompatibilityInstaller
from tf3_early_start_manager.scanner import (
    SCAN_CACHE_SCHEMA_VERSION,
    ScanCache,
)
from tf3_early_start_manager.scanner.service import ScannerService
from tf3_early_start_manager.tf3 import InstallationService
from tf3_early_start_manager.tf3.patch_state import PatchService as PatchStateService
from tf3_early_start_manager.tf3.gui_patch import PatchService as GuiPatchService
from tf3_early_start_manager.tf3 import start_game as launch_tf3




from tf3_early_start_manager.scanner.classifier import vehicle_navigation_category




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


from tf3_early_start_manager.scanner.worker import ContentScanWorker


class ScanProgressDialog(QDialog):
    cancel_requested = Signal()

    def __init__(self, translator, parent=None):
        super().__init__(parent)
        self._tr = translator
        self.setWindowTitle(self._tr("scan.window_title"))
        self.setModal(True)
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        self.title_label = QLabel(self._tr("scan.preparing"))
        self.title_label.setObjectName("section")
        self.detail_label = QLabel("")
        self.detail_label.setWordWrap(True)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.stats_label = QLabel(self._tr("scan.initial_progress"))
        self.cancelled_by_user = False
        self.cancel_button = QPushButton(self._tr("actions.cancel"))
        self.cancel_button.clicked.connect(self._request_cancel)
        layout.addWidget(self.title_label)
        layout.addWidget(self.detail_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.stats_label)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(self.cancel_button)
        layout.addLayout(row)

    def _request_cancel(self):
        self.cancelled_by_user = True
        self.cancel_button.setEnabled(False)
        self.cancel_button.setText(self._tr("scan.cancelling"))
        self.cancel_requested.emit()

    def closeEvent(self, event):
        if self.cancel_button.isEnabled():
            self._request_cancel()
            event.ignore()
        else:
            event.ignore()

    @Slot(int, int, str, str, int, int, int)
    def update_progress(self, current: int, total: int, domain: str, zip_name: str, found: int, cache_hits: int, rescanned: int):
        percent = int(current * 100 / total) if total else 0
        self.progress_bar.setValue(percent)
        self.title_label.setText(self._tr("scan.scanning", domain=domain or self._tr("scan.finishing")))
        self.detail_label.setText(zip_name)
        self.stats_label.setText(
            self._tr("scan.progress", current=current, total=total, cache_hits=cache_hits, rescanned=rescanned, found=found)
        )



from tf3_early_start_manager.localization import (
    LanguageResolver,
    canonical_language,
    initial_ui_language,
)


class MainWindow(QMainWindow):
    C_STATUS = 0
    C_NAME = 1
    C_SOURCE = 2
    C_DOMAIN = 3
    C_CATEGORY = 4
    C_TYPE = 5
    C_MODIFIER = 6
    C_FROM = 7
    C_NEW = 8
    C_TO = 9
    C_RESOURCE = 10

    def __init__(self) -> None:
        super().__init__()
        LOGGER.info("Application startup version=%s", APP_VERSION)
        self.LOGGER = LOGGER
        self.settings = QSettings("TF3EarlyStartManager", "TF3EarlyStartManager")
        self.resources: list[Resource] = []
        self.resource_tree_expanded = False
        self.installation: Installation | None = None
        self.installations = InstallationService()
        self.patch_state_service = PatchStateService(self)
        self.gui_patch_service = GuiPatchService(self)
        self.compatibility_analyzer = CompatibilityAnalyzer(self)
        self.compatibility_generator = CompatibilityGenerator(self, APP_ROOT)
        self.compatibility_installer = CompatibilityInstaller(self)
        self.language = initial_ui_language(self.settings)
        self.i18n = LanguageResolver(self.language, RESOURCE_ROOT / "languages")
        self.scanner = ScannerService(self)
        self.resource_tree_controller = ResourceTreeController(self)
        self.resource_preview_controller = ResourcePreviewController(self, APP_ROOT)
        self.resource_selection_controller = ResourceSelectionController(self)
        self.header_controller = HeaderController(self)
        self.settings_dialog_controller = SettingsDialogController(self, APP_ROOT, LOG_DIR, LOG_FILE)
        self.easy_mode_builder = EasyModeBuilder(self)
        self.advanced_mode_builder = AdvancedModeBuilder(self)
        self.tf3_translations: gettext.NullTranslations = gettext.NullTranslations()
        self._patch_health_cache: tuple[str, str] | None = None
        self._tf3_build_info_cache: dict[str, str] | None = None
        self._tf3_executable_fingerprint_cache: dict | None = None
        self._startup_started = time.perf_counter()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(1500, 900)
        self._build_ui()
        self._restore_installation()
        self.cleanup_legacy_build_learning()
        self.migrate_legacy_scan_cache()
        self.load_cached_resources_on_startup()
        self.apply_styles()
        self.refresh_easy_status()
        self.refresh_source_status()
        self.warn_if_patch_needs_attention()
        LOGGER.info("PERF startup total %.3fs resources=%d", time.perf_counter() - self._startup_started, len(self.resources))

    def tr(self, key: str, **values) -> str:
        return self.i18n.ui(key, **values)

    def localized_content(self, values, *, raw: str = "", identifier: str = "") -> str:
        return self.i18n.content(values, raw=raw, identifier=identifier)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        layout.addWidget(self._header())

        self.mode_stack = QStackedWidget()
        self.mode_stack.addWidget(self._easy_page())
        self.mode_stack.addWidget(self._advanced_page())
        layout.addWidget(self.mode_stack, 1)

        if str(self.settings.value("start_mode", "easy")) == "advanced":
            self.show_advanced_mode()
        else:
            self.show_easy_mode()


    def _header(self) -> QWidget:
        return self.header_controller._header()

    def sync_header_status(self) -> None:
        return self.header_controller.sync_header_status()

    def open_settings(self) -> None:
        return self.settings_dialog_controller.open_settings()

    def refresh_easy_status(self) -> None:
        return self.header_controller.refresh_easy_status()



    def _build_resource_tree(self) -> None:
        self.resource_tree.clear()
        all_item = QTreeWidgetItem([self.tr("resource_tree.all")])
        all_item.setData(0, Qt.ItemDataRole.UserRole, ("all", None))
        self.resource_tree.addTopLevelItem(all_item)
        labels = {
            "vehicle": self.tr("resource_tree.vehicle"),
            "depots": self.tr("resource_tree.depots"),
            "stations": self.tr("resource_tree.stations"),
            "warehouses": self.tr("resource_tree.warehouses"),
            "infrastructure": self.tr("resource_tree.infrastructure"),
            "buildings": self.tr("resource_tree.buildings"),
            "industries": self.tr("resource_tree.industries"),
            "assets": self.tr("resource_tree.assets"),
        }
        for domain in SCAN_DOMAINS:
            top = QTreeWidgetItem([labels[domain]])
            top.setData(0, Qt.ItemDataRole.UserRole, (domain, None))
            self.resource_tree.addTopLevelItem(top)
        self.resource_tree.setCurrentItem(all_item)

    def invalidate_health_cache(self, reason: str = "manual") -> None:
        self._patch_health_cache = None
        self._tf3_build_info_cache = None
        self._tf3_executable_fingerprint_cache = None
        LOGGER.debug("HEALTH_CACHE invalidated reason=%s", reason)

    # ------------------------------------------------------------------
    # Settings / modes
    # ------------------------------------------------------------------
    def toggle_mode(self) -> None:
        if self.mode_stack.currentIndex() == 0:
            self.show_advanced_mode()
        else:
            self.show_easy_mode()

    def _easy_page(self) -> QWidget:
        return self.easy_mode_builder._easy_page()

    def _advanced_page(self) -> QWidget:
        return self.advanced_mode_builder._advanced_page()

    def show_easy_mode(self) -> None:
        started = time.perf_counter()
        self.mode_stack.setCurrentIndex(0)
        self.mode_button.setText(self.tr("mode.advanced"))
        if hasattr(self, "header_status_widget"):
            self.header_status_widget.hide()
        LOGGER.info("PERF mode easy %.4fs", time.perf_counter() - started)

    def show_advanced_mode(self) -> None:
        started = time.perf_counter()
        self.mode_stack.setCurrentIndex(1)
        self.mode_button.setText(self.tr("mode.easy"))
        if hasattr(self, "header_status_widget"):
            self.header_status_widget.show()
        LOGGER.info("PERF mode advanced %.4fs", time.perf_counter() - started)



    # ------------------------------------------------------------------
    # Installation / game launch
    # ------------------------------------------------------------------







    def _restore_installation(self) -> None:
        saved = str(self.settings.value("game_path", "")).strip()
        if saved:
            self.installation = self.validate_installation(Path(saved))
        if self.installation:
            return
        for candidate in self.installation_candidates():
            inst = self.validate_installation(candidate)
            if inst:
                self.installation = inst
                self.settings.setValue("game_path", str(inst.root))
                self.settings.setValue("game_distribution", inst.distribution)
                return

    def validate_installation(self, root: Path) -> Installation | None:
        return self.installations.validate_installation(root)

    def installation_candidates(self) -> list[Path]:
        return self.installations.installation_candidates()

    def steam_root(self) -> Path | None:
        self.installations.installation = self.installation
        return self.installations.steam_root()

    def userdata_mods_dir(self) -> Path:
        self.installations.installation = self.installation
        return self.installations.userdata_mods_dir()

    def cleanup_legacy_build_learning(self) -> None:
        for key in (
            "tf3_internal_build", "tf3_build_exe_sha256",
            "tf3_build_stdout_path", "tf3_build_stdout_mtime_ns",
        ):
            self.settings.remove(key)
        self.settings.sync()










    def record_source_snapshot(self) -> None:
        snapshot = self.scanner.cheap_source_snapshot()
        self.settings.setValue(
            "source_snapshot",
            json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")),
        )
        self.settings.sync()
        self.refresh_source_status(snapshot)

    def refresh_source_status(self, current_snapshot: dict | None = None) -> None:
        if not hasattr(self, "source_status"):
            return
        if not self.installation:
            self.source_status.setText(self.tr("status.tf3_not_configured"))
            self.source_status.setStyleSheet("color:#f0b35a;")
            return
        current = current_snapshot or self.scanner.cheap_source_snapshot()
        raw_previous = str(self.settings.value("source_snapshot", "")).strip()
        try:
            previous = json.loads(raw_previous) if raw_previous else None
        except json.JSONDecodeError:
            previous = None
        gui_state = self.gui_state()
        patch_health, patch_detail = self.patch_health()
        if previous is None:
            # Establish a baseline without forcing work on first launch after upgrade.
            self.settings.setValue(
                "source_snapshot",
                json.dumps(current, ensure_ascii=False, separators=(",", ":")),
            )
            self.settings.sync()
            changed_sections: list[str] = []
        else:
            changed_sections = [
                section for section in ("vanilla", "modio", "local")
                if previous.get(section) != current.get(section)
            ]
        stale_overrides = self.stale_installed_override_count() if self.resources else 0
        if patch_health in {"update_vanilla", "exe_changed_patch_intact", "changed", "legacy"}:
            self.source_status.setText(self.tr("status.patch_revalidation_required"))
            self.source_status.setToolTip(patch_detail)
            self.source_status.setStyleSheet("color:#f0b35a;font-weight:600;")
        elif gui_state == "vanilla":
            self.source_status.setText(self.tr("status.patch_missing"))
            self.source_status.setToolTip(
                self.tr("tooltips.patch_missing")
            )
            self.source_status.setStyleSheet("color:#f0b35a;font-weight:600;")
        elif stale_overrides:
            self.source_status.setText(self.tr("status.compatibility_update_required"))
            self.source_status.setToolTip(
                self.tr("tooltips.stale_overrides", count=stale_overrides)
            )
            self.source_status.setStyleSheet("color:#f0b35a;font-weight:600;")
        elif changed_sections:
            labels = {"vanilla": "TF3", "modio": "Mod.IO", "local": "Local"}
            changed_text = ", ".join(labels[item] for item in changed_sections)
            self.source_status.setText(self.tr("status.changes_detected"))
            self.source_status.setToolTip(
                self.tr("tooltips.changed_sources", sources=changed_text)
            )
            self.source_status.setStyleSheet("color:#f0b35a;font-weight:600;")
        else:
            self.source_status.setText(self.tr("status.content_up_to_date"))
            self.source_status.setToolTip(
                self.tr("tooltips.no_source_changes")
            )
            self.source_status.setStyleSheet("color:#65c97a;font-weight:600;")

    def refresh_all_status(self) -> None:
        self.invalidate_health_cache("refresh-status")
        self.refresh_easy_status()
        self.refresh_source_status()

    def start_game(self) -> None:
        if not self.installation:
            QMessageBox.warning(self, self.tr("dialogs.start_game_title"), self.tr("dialogs.configure_tf3_first"))
            return
        try:
            launch_tf3(self.installation)
        except (OSError, RuntimeError) as exc:
            QMessageBox.critical(self, self.tr("dialogs.start_game_title"), str(exc))


    def load_tf3_translations(self) -> None:
        """Load TF3 gettext catalogs as selected language -> English fallback."""
        self.tf3_translations = gettext.NullTranslations()
        if not self.installation:
            return
        search_roots = (self.installation.root / "base", self.installation.root / "base" / "content")

        def matching_mo_files(language: str) -> list[Path]:
            aliases = tuple(alias.lower() for alias in self.i18n.language_keys(language))
            found: list[Path] = []
            for root in search_roots:
                if not root.is_dir():
                    continue
                for mo in root.rglob("*.mo"):
                    low = str(mo).lower().replace("\\", "/")
                    if any(f"/{alias}/" in low or alias in mo.name.lower() for alias in aliases):
                        found.append(mo)
            return sorted(set(found), key=lambda path: str(path).lower())

        def merged(language: str) -> gettext.NullTranslations | None:
            current = None
            for mo in matching_mo_files(language):
                try:
                    with mo.open("rb") as handle:
                        catalog = gettext.GNUTranslations(handle)
                except (OSError, EOFError, UnicodeError):
                    continue
                if current is None:
                    current = catalog
                else:
                    current.add_fallback(catalog)
            return current

        selected = merged(self.language)
        english = merged("en") if self.language != "en" else None
        if selected is not None:
            if english is not None:
                selected.add_fallback(english)
            self.tf3_translations = selected
        elif english is not None:
            self.tf3_translations = english




    # ------------------------------------------------------------------
    # Generic availability scanner
    # ------------------------------------------------------------------













    def select_all_resources(self):
        return self.resource_tree_controller.select_all_resources()

    def toggle_resource_tree_expansion(self):
        return self.resource_tree_controller.toggle_resource_tree_expansion()

    def _rebuild_tree_categories(self):
        return self.resource_tree_controller._rebuild_tree_categories()

    def selected_scope(self):
        return self.resource_tree_controller.selected_scope()

    def active_source_types(self):
        return self.resource_tree_controller.active_source_types()

    def thumbnail_cache_dir(self):
        return self.resource_preview_controller.thumbnail_cache_dir()

    def cached_thumbnail(self, resource: Resource):
        return self.resource_preview_controller.cached_thumbnail(resource)

    def update_resource_preview(self, proxy_index: QModelIndex):
        return self.resource_preview_controller.update_resource_preview(proxy_index)

    def resource_at_view_position(self, position):
        return self.resource_preview_controller.resource_at_view_position(position)

    @staticmethod
    def resource_filesystem_target(resource: Resource):
        return ResourcePreviewController.resource_filesystem_target(resource)

    @staticmethod
    def explorer_select(path: Path):
        return ResourcePreviewController.explorer_select(path)

    @staticmethod
    def copy_text(text: str):
        return ResourcePreviewController.copy_text(text)

    def open_resource_context_menu(self, position):
        return self.resource_preview_controller.open_resource_context_menu(position)

    def visible_resource_count(self):
        return self.resource_selection_controller.visible_resource_count()

    def update_resource_count(self):
        return self.resource_selection_controller.update_resource_count()

    def _set_proxy_values(self):
        return self.resource_selection_controller._set_proxy_values()

    def apply_resource_filter(self):
        return self.resource_selection_controller.apply_resource_filter()

    def update_overview_or_count(self):
        return self.resource_selection_controller.update_overview_or_count()

    def selected_resource_objects(self):
        return self.resource_selection_controller.selected_resource_objects()

    def _finish_resource_batch_update(self, resources: list[Resource]):
        return self.resource_selection_controller._finish_resource_batch_update(resources)

    def set_selected_year(self):
        return self.resource_selection_controller.set_selected_year()

    def reset_selected(self):
        return self.resource_selection_controller.reset_selected()

    def scan_cache_summary(self) -> tuple[int, int, int]:
        data = self.load_scan_cache()
        archives = data.get("archives", {}) if isinstance(data, dict) else {}
        if not isinstance(archives, dict):
            return 0, 0, 0
        archive_count = len(archives)
        resource_count = 0
        for entry in archives.values():
            if isinstance(entry, dict) and isinstance(entry.get("resources"), list):
                resource_count += len(entry["resources"])
        path = self.scan_cache_path()
        return archive_count, resource_count, path.stat().st_size if path.is_file() else 0



    def load_cached_resources_on_startup(self) -> None:
        """Populate Advanced Mode immediately from cache without requiring Scan Content."""
        if not self.installation:
            return
        data = self.load_scan_cache()
        archives = data.get("archives", {}) if isinstance(data, dict) else {}
        if not isinstance(archives, dict) or not archives:
            return
        resources: list[Resource] = []
        for entry in archives.values():
            if not isinstance(entry, dict):
                continue
            resources.extend(self.resources_from_cache(entry.get("resources", [])))
        if not resources:
            return
        self.resources = resources
        self._merge_installed_overrides()
        self._rebuild_tree_categories()
        self.select_all_resources()
        self.resource_model.set_resources(self.resources)
        self.apply_resource_filter()
        self.resource_count.setText(self.tr("status.resources_loaded_cache", count=len(self.resources)))

    def scan_cache_service(self) -> ScanCache:
        return ScanCache(APP_ROOT, self.language, self.installation)

    def scan_cache_path(self) -> Path:
        return self.scan_cache_service().path

    def migrate_legacy_scan_cache(self) -> None:
        self.scan_cache_service().migrate_legacy()

    def load_scan_cache(self) -> dict:
        return self.scan_cache_service().load()

    def save_scan_cache(self, data: dict) -> None:
        self.scan_cache_service().save(data)

    @staticmethod
    def resource_to_cache(r: Resource) -> dict:
        return ScanCache.resource_to_dict(r)

    def resources_from_cache(self, rows) -> list[Resource]:
        return ScanCache.resources_from_rows(rows, EARLY_START_CONSTRUCTION_PRESET, EARLY_START_CAR_PRESET)

    def clear_scan_cache(self) -> None:
        self.scan_cache_service().clear()

    def scan_content(self) -> None:
        LOGGER.info("CONTENT_SCAN requested force=%s", self.force_rescan.isChecked() if hasattr(self, "force_rescan") else False)
        if not self.installation:
            QMessageBox.warning(self, self.tr("dialogs.scan_title"), self.tr("dialogs.configure_tf3_first"))
            return
        if getattr(self, "scan_thread", None) is not None and self.scan_thread.isRunning():
            return

        # Translation catalogs are prepared on the UI thread. The worker then
        # performs only read-only archive/file processing.
        self.load_tf3_translations()
        self.scan_dialog = ScanProgressDialog(self.tr, self)
        self.scan_thread = QThread(self)
        self.scan_worker = ContentScanWorker(self.scanner, self.installation, self.force_rescan.isChecked())
        self.scan_worker.moveToThread(self.scan_thread)
        self.scan_thread.started.connect(self.scan_worker.run)
        self.scan_worker.progress.connect(self.scan_dialog.update_progress)
        self.scan_dialog.cancel_requested.connect(self.scan_worker.cancel, Qt.ConnectionType.DirectConnection)
        self.scan_worker.finished.connect(self._scan_finished)
        self.scan_worker.failed.connect(self._scan_failed)
        self.scan_worker.cancelled.connect(self._scan_cancelled)
        self.scan_worker.finished.connect(self.scan_thread.quit)
        self.scan_worker.failed.connect(self.scan_thread.quit)
        self.scan_worker.cancelled.connect(self.scan_thread.quit)
        self.scan_thread.finished.connect(self._scan_thread_finished)
        LOGGER.info("CONTENT_SCAN starting worker thread")
        self.scan_thread.start()
        self.scan_dialog.show()

    @Slot(object)
    def _scan_finished(self, found):
        LOGGER.info("CONTENT_SCAN worker finished resources=%d",len(found)); self._pending_scan_resources=list(found); self._scan_prepare_stage=0; self._scan_prepare_started=time.perf_counter()
        if self.scan_dialog: self.scan_dialog.progress_bar.setValue(100); self.scan_dialog.title_label.setText(self.tr("scan.preparing_browser"))
        QTimer.singleShot(0,self._continue_scan_preparation)
    @Slot()
    def _continue_scan_preparation(self):
        d=getattr(self,"scan_dialog",None)
        if d and d.cancelled_by_user: self._pending_scan_resources=[]; d.reject(); self.scan_dialog=None; return
        stage=self._scan_prepare_stage
        if stage==0: self.resources=self._pending_scan_resources; self._merge_installed_overrides()
        elif stage==1: self._rebuild_tree_categories(); self.select_all_resources()
        elif stage==2:
            h=self.resource_table.horizontalHeader(); section=h.sortIndicatorSection(); order=h.sortIndicatorOrder(); self.resource_proxy.setDynamicSortFilter(False)
            self.resource_model.set_resources(self.resources); self._set_proxy_values(); self.resource_proxy.refilter_rows(); self.resource_proxy.sort(section,order); self.resource_proxy.setDynamicSortFilter(True)
        else:
            self.update_overview_or_count(); self.record_source_snapshot(); LOGGER.info("CONTENT_SCAN browser ready %.3fs",time.perf_counter()-self._scan_prepare_started); self._pending_scan_resources=[]
            if d: d.accept(); self.scan_dialog=None
            return
        self._scan_prepare_stage+=1; QTimer.singleShot(0,self._continue_scan_preparation)
    @Slot(str)
    def _scan_failed(self, message: str):
        LOGGER.error("CONTENT_SCAN failed %s", message)
        if getattr(self, "scan_dialog", None):
            self.scan_dialog.reject()
        QMessageBox.critical(self, self.tr("dialogs.content_scan_title"), message)

    @Slot()
    def _scan_cancelled(self):
        if getattr(self, "scan_dialog", None):
            self.scan_dialog.reject()

    @Slot()
    def _scan_thread_finished(self):
        LOGGER.info("CONTENT_SCAN worker thread finished")
        if getattr(self, "scan_worker", None) is not None:
            self.scan_worker.deleteLater()
        if getattr(self, "scan_thread", None) is not None:
            self.scan_thread.deleteLater()
        self.scan_worker = None
        self.scan_thread = None
        if not getattr(self,"_pending_scan_resources",[]): self.scan_dialog = None

    def _merge_installed_overrides(self) -> None:
        try:
            path = self.userdata_mods_dir() / COMPATIBILITY_MOD_ID / "overrides.json"
            data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        except (OSError, RuntimeError, json.JSONDecodeError):
            data = {}
        overrides = {x.get("resourceId"): x for x in data.get("overrides", []) if isinstance(x, dict)}
        for r in self.resources:
            if r.locked or r.internal:
                continue
            item = overrides.get(r.resource_id, {})
            if isinstance(item.get("newYearFrom"), int):
                r.new_year_from = item["newYearFrom"]
            if isinstance(item.get("newYearTo"), int):
                r.new_year_to = item["newYearTo"]



    @staticmethod
    def display_year(resource: Resource, value: int) -> str:
        return "Internal" if value >= INTERNAL_YEAR_SENTINEL else str(value)

    def toggle_all_sources(self, checked: bool) -> None:
        for checkbox in (self.source_vanilla, self.source_modio, self.source_local):
            checkbox.blockSignals(True)
            checkbox.setChecked(checked)
            checkbox.blockSignals(False)
        if checked:
            self.apply_resource_filter()


    def _show_all_resources_changed(self, checked: bool) -> None:
        self.settings.setValue("show_all_resources", checked)
        self.settings.sync()

        self._rebuild_tree_categories()
        self.apply_resource_filter()











    def stale_installed_override_count(self) -> int:
        manifest = self.installed_manifest()
        installed_ids = {
            str(item.get("resourceId"))
            for item in manifest.get("overrides", [])
            if isinstance(item, dict) and item.get("resourceId")
        }
        current_ids = {resource.resource_id for resource in self.resources}
        # Warehouse resource overrides are generated independently from scan rows.
        current_ids.update(WAREHOUSE_OVERRIDE_IDS)
        return len(installed_ids - current_ids)





    # ------------------------------------------------------------------
    # Companion runtime mod
    # ------------------------------------------------------------------



    def changed_supported_resources(self) -> list[Resource]:
        return self.compatibility_analyzer.changed_supported_resources()

    def generate_compatibility_mod(self, resources: Iterable[Resource]) -> Path:
        return self.compatibility_generator.generate_compatibility_mod(resources)

    def install_generated_mod(self, generated: Path) -> None:
        self.compatibility_installer.install_generated_mod(generated)

    def installed_manifest(self) -> dict:
        return self.compatibility_installer.installed_manifest()

    def install_current_overrides(self) -> None:
        self.invalidate_health_cache("compat-update-start")
        try:
            LOGGER.info("INSTALL_COMPAT start")

            resources = self.changed_supported_resources()
            LOGGER.info(
                "INSTALL_COMPAT changed resources=%d",
                len(resources),
            )

            generated = self.generate_compatibility_mod(resources)
            LOGGER.info(
                "INSTALL_COMPAT generated=%s",
                generated,
            )

            self.install_generated_mod(generated)
            LOGGER.info("INSTALL_COMPAT installed")

            self.refresh_source_status()
            self.refresh_easy_status()

            QMessageBox.information(
                self,
                self.tr("dialogs.compatibility_title"),
                self.tr("dialogs.compatibility_installed"),
            )

            LOGGER.info("INSTALL_COMPAT done")

        except Exception as exc:
            LOGGER.exception(
                "Install / Update Compatibility Mod failed"
            )

            QMessageBox.critical(
                self,
                self.tr("dialogs.compatibility_title"),
                self.tr("dialogs.install_update_failed", error=exc),
            )

    # ------------------------------------------------------------------
    # Easy profile + gui.zip
    # ------------------------------------------------------------------














    def tf3_executable(self):
        return self.patch_state_service.tf3_executable()

    @staticmethod
    def windows_file_version(path: Path):
        return PatchStateService.windows_file_version(path)

    def tf3_build_info(self):
        return self.patch_state_service.tf3_build_info()

    def tf3_build_version(self):
        return self.patch_state_service.tf3_build_version()

    def tf3_executable_fingerprint(self):
        return self.patch_state_service.tf3_executable_fingerprint()

    @staticmethod
    def executable_changed(stored: dict, current: dict):
        return PatchStateService.executable_changed(stored, current)

    @staticmethod
    def sha256_file(path: Path):
        return PatchStateService.sha256_file(path)

    def patch_state_path(self):
        return self.patch_state_service.patch_state_path()

    def load_patch_state(self):
        return self.patch_state_service.load_patch_state()

    @staticmethod
    def patch_state_snapshot(state: dict, reason: str):
        return PatchStateService.patch_state_snapshot(state, reason)

    def save_patch_state(self, state: dict):
        return self.patch_state_service.save_patch_state(state)

    def archive_patch_generation(self, state: dict, reason: str):
        return self.patch_state_service.archive_patch_generation(state, reason)

    def patch_health(self):
        return self.patch_state_service.patch_health()

    def _compute_patch_health(self):
        return self.patch_state_service._compute_patch_health()

    def gui_backup(self):
        return self.patch_state_service.gui_backup()

    def gui_state(self):
        return self.patch_state_service.gui_state()

    @staticmethod
    def find_central(raw: bytearray, name: str):
        return GuiPatchService.find_central(raw, name)

    def patch_gui(self):
        return self.gui_patch_service.patch_gui()

    def warn_if_patch_needs_attention(self) -> None:
        if not self.installation: return
        status, message = self.patch_health()
        if status in {"changed", "legacy", "update_vanilla", "exe_changed_patch_intact"}:
            QTimer.singleShot(0, lambda: QMessageBox.warning(self, self.tr("dialogs.patch_verification_title"), message + "\n\n" + self.tr("dialogs.patch_verification_safety")))





    def install_easy_patch(self) -> None:
        if not self.installation:
            QMessageBox.warning(self, self.tr("dialogs.patch_title"), self.tr("dialogs.configure_tf3_first"))
            return
        try:
            self.patch_gui()
            if not self.resources:
                self.load_cached_resources_on_startup()
            if not self.resources:
                raise RuntimeError("No content scan data available. Run Scan Content once, then install the 1850 patch again.")
            # v0.6.2 Easy Mode explicitly applies the tested historical baseline.
            # Advanced Mode may add further user overrides, but Easy Mode always
            # includes these required/default 1850 resources.
            for resource in self.resources:
                vehicle_id = Path(resource.internal_path).stem.split(".")[0]
                if resource.source_type == "vanilla" and resource.domain == "vehicle" and vehicle_id in EARLY_START_CAR_PRESET:
                    resource.new_year_from = EARLY_START_CAR_PRESET[vehicle_id]
                    resource.locked = True
                construction_year = EARLY_START_CONSTRUCTION_PRESET.get(resource.resource_id) if resource.source_type == "vanilla" else None
                if construction_year is not None:
                    resource.new_year_from = construction_year
                    resource.locked = True
            generated = self.generate_compatibility_mod(self.changed_supported_resources())
            self.install_generated_mod(generated)
            self.refresh_easy_status()
            self.refresh_source_status()
            QMessageBox.information(self, self.tr("dialogs.patch_title"), self.tr("dialogs.patch_installed"))
        except (RuntimeError, OSError, shutil.Error) as exc:
            QMessageBox.critical(self, self.tr("dialogs.patch_title"), str(exc))

    def revert_easy_patch(self) -> None:
        self.invalidate_health_cache("revert-patch-start")
        if not self.installation:
            return
        try:
            backup = self.gui_backup()
            health, _message = self.patch_health(); state = self.load_patch_state()
            current_exe = self.tf3_executable_fingerprint()
            if health in {"changed", "update_vanilla", "legacy"} or self.executable_changed(state.get("tf3Executable", {}), current_exe):
                raise RuntimeError("TF3 version/files changed. Refusing to restore an old gui.zip backup.")
            if backup.is_file():
                backup_hash = self.sha256_file(backup); expected_hash = state.get("backupSha256") if state else None
                if expected_hash and backup_hash != expected_hash: raise RuntimeError("Backup SHA-256 does not match the recorded patch state.")
                shutil.copy2(backup, self.installation.gui_zip)
            if self.patch_state_path().is_file(): self.patch_state_path().unlink()
            mod = self.userdata_mods_dir() / COMPATIBILITY_MOD_ID
            if mod.exists():
                shutil.rmtree(mod)
            self.refresh_easy_status()
            self.refresh_source_status()
        except (RuntimeError, OSError, shutil.Error) as exc:
            QMessageBox.critical(self, self.tr("actions.revert_patch"), str(exc))



    def apply_styles(self) -> None:
        self.setStyleSheet("""
            QMainWindow {
                background: #181b20;
                color: #e8ebef;
                font-size: 10pt;
            }

            QWidget {
                color: #e8ebef;
                font-size: 10pt;
            }

            QFrame#panel {
                background: #22262c;
                border: 1px solid #363b44;
                border-radius: 6px;
            }

            QLabel {
                background: transparent;
                color: #e8ebef;
            }

            QLabel#title {
                background: transparent;
                color: #e8ebef;
                font-size: 18pt;
                font-weight: 700;
            }

            QLabel#section {
                background: transparent;
                color: #e8ebef;
                font-size: 13pt;
                font-weight: 700;
            }

            QLabel#muted,
            QLabel#helpText {
                background: transparent;
                color: #e8ebef;
            }

            QLabel#overall {
                background: transparent;
                padding-top: 8px;
                font-weight: 700;
            }

            QCheckBox {
                background: transparent;
                color: #e8ebef;
            }

            QPushButton {
                color: #e8ebef;
                background: #30353d;
                border: 1px solid #454b55;
                border-radius: 4px;
                padding: 6px 10px;
            }

            QPushButton:hover {
                background: #3a414b;
            }

            QPushButton#primary {
                background: #1769aa;
                border-color: #267fc2;
                font-weight: 600;
            }

            QLineEdit,
            QComboBox,
            QSpinBox {
                color: #e8ebef;
                background: #20242a;
                border: 1px solid #424852;
                border-radius: 4px;
                padding: 5px;
            }

            QTreeWidget,
            QTableView {
                color: #e8ebef;
                background: #1d2025;
                alternate-background-color: #23272d;
                border: 1px solid #363b44;
                gridline-color: #333842;
            }

            QTreeWidget::item:selected,
            QTableView::item:selected {
                background: #285d88;
            }

            QHeaderView::section {
                color: #e8ebef;
                background: #292e35;
                padding: 6px;
                border: 0;
                border-right: 1px solid #414650;
                font-weight: 600;
            }
        """)
