from __future__ import annotations
from tf3_early_start_manager.version import APP_NAME, APP_VERSION
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame,QHBoxLayout,QLabel,QPushButton,QVBoxLayout,QWidget
from tf3_early_start_manager.compatibility.analyzer import EARLY_START_CAR_PRESET, EARLY_START_CONSTRUCTION_PRESET
WAREHOUSE_OVERRIDE_IDS={f"::/warehouses/{name}":1850 for name in ("warehouse_era_a_bulk.metacon.tl","warehouse_era_a_flatbed.metacon.tl","warehouse_era_a_goods.metacon.tl","warehouse_era_a_liquid.metacon.tl","warehouse_era_a_universal.metacon.tl")}

class HeaderController:
    def __init__(self,host):
        object.__setattr__(self,"host",host)
    def __getattr__(self,name):
        return getattr(self.host,name)
    def __setattr__(self,name,value):
        setattr(self.host,name,value)

    def _header(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("panel")

        row = QHBoxLayout(frame)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(16)

        # --------------------------------------------------
        # Left: title / subtitle
        # --------------------------------------------------

        title_col = QVBoxLayout()
        title_col.setSpacing(4)

        title = QLabel(APP_NAME)
        title.setObjectName("title")

        subtitle = QLabel(self.tr("app.subtitle"))
        subtitle.setObjectName("muted")

        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        title_col.addStretch()

        row.addLayout(title_col, 1)

        # --------------------------------------------------
        # Center: Early Start status
        # --------------------------------------------------

        self.header_status_widget = QWidget()
        status_col = QVBoxLayout(self.header_status_widget)
        status_col.setContentsMargins(0, 0, 0, 0)
        status_col.setSpacing(2)

        self.header_gui_status = QLabel()
        self.header_backup_status = QLabel()
        self.header_mod_status = QLabel()
        self.header_profile_status = QLabel()

        for widget in (
            self.header_gui_status,
            self.header_backup_status,
            self.header_mod_status,
            self.header_profile_status,
        ):
            widget.setStyleSheet(
                "background: transparent; color: #e8ebef;"
            )
            status_col.addWidget(widget)

        patch_actions = QHBoxLayout()
        patch_actions.setContentsMargins(0, 4, 0, 0)
        patch_actions.setSpacing(8)
        header_install_patch = QPushButton(self.tr("actions.install_patch"))
        header_install_patch.setToolTip(self.tr("tooltips.install_patch"))
        header_install_patch.clicked.connect(self.install_easy_patch)
        header_revert_patch = QPushButton(self.tr("actions.revert_patch"))
        header_revert_patch.setToolTip(self.tr("tooltips.revert_patch"))
        header_revert_patch.clicked.connect(self.revert_easy_patch)
        self.header_install_patch_button = header_install_patch
        self.header_revert_patch_button = header_revert_patch
        patch_actions.addWidget(header_install_patch)
        patch_actions.addWidget(header_revert_patch)
        patch_actions.addStretch()
        status_col.addLayout(patch_actions)
        status_col.addStretch()

        row.addWidget(self.header_status_widget, 2)

        # --------------------------------------------------
        # Right: version / language / controls
        # --------------------------------------------------

        right = QVBoxLayout()
        right.setAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignVCenter
        )

        self.version_label = QLabel(
            self.tr("app.version", version=APP_VERSION)
        )

        self.language_label = QLabel(self.tr("language.current", language=self.tr("language.name")))

        self.version_label.setAlignment(
            Qt.AlignmentFlag.AlignRight
        )
        self.language_label.setAlignment(
            Qt.AlignmentFlag.AlignRight
        )

        right.addWidget(self.version_label)
        right.addWidget(self.language_label)

        buttons = QHBoxLayout()

        self.settings_button = QPushButton(self.tr("actions.settings"))
        self.settings_button.clicked.connect(
            self.open_settings
        )

        self.mode_button = QPushButton(self.tr("mode.advanced"))
        self.mode_button.clicked.connect(
            self.toggle_mode
        )

        exit_button = QPushButton(self.tr("actions.exit"))
        exit_button.clicked.connect(
            self.close
        )

        buttons.addWidget(
            self.settings_button
        )
        buttons.addWidget(
            self.mode_button
        )
        buttons.addWidget(
            exit_button
        )

        right.addLayout(buttons)

        row.addLayout(right)

        return frame

    def sync_header_status(self) -> None:
        if not hasattr(self, "header_gui_status"):
            return

        self.header_gui_status.setText(
            self.easy_gui.text()
        )
        self.header_backup_status.setText(
            self.easy_backup.text()
        )
        self.header_mod_status.setText(
            self.easy_mod.text()
        )
        self.header_profile_status.setText(
            self.easy_profile.text()
        )

    @staticmethod
    def _set_primary(button, enabled: bool) -> None:
        if button is None:
            return
        button.setObjectName("primary" if enabled else "")
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()

    def refresh_primary_actions(self, patch_ready: bool) -> None:
        """Highlight the next setup action consistently across Easy/Advanced UI."""
        self._set_primary(getattr(self, "easy_install_patch_button", None), not patch_ready)
        self._set_primary(getattr(self, "header_install_patch_button", None), not patch_ready)
        self._set_primary(getattr(self, "easy_update_compat_button", None), patch_ready)
        self._set_primary(getattr(self, "advanced_update_compat_button", None), patch_ready)

    def refresh_easy_status(self) -> None:
        if not self.installation:
            self.easy_game.setText(self.tr("health.game_not_detected"))
            for x in (self.easy_gui, self.easy_backup, self.easy_mod, self.easy_profile):
                x.setText(self.tr("health.unavailable"))
            self.easy_overall.setText(self.tr("health.not_ready"))
            self.refresh_primary_actions(False)
            self.sync_header_status()
            return
        self.easy_game.setText(self.tr("health.game_detected", distribution=self.installation.distribution, path=self.installation.root))
        state = self.gui_state(); patch_health, patch_detail = self.patch_health()
        labels = {
            "verified": self.tr("health.patch_verified"),
            "legacy": self.tr("health.patch_revalidation"),
            "vanilla": self.tr("health.patch_vanilla"),
            "update_vanilla": self.tr("health.patch_rebuild"),
            "exe_changed_patch_intact": self.tr("health.patch_revalidate"),
            "changed": self.tr("health.patch_changed"),
            "unavailable": self.tr("health.patch_unavailable"),
        }
        self.easy_gui.setText(labels.get(patch_health, self.tr("health.patch_unknown"))); self.easy_gui.setToolTip(patch_detail)
        self.easy_backup.setText(self.tr("health.backup_available") if self.gui_backup().is_file() else self.tr("health.backup_missing"))
        manifest = self.installed_manifest()
        count = len(manifest.get("overrides", []))
        mod_ok = count > 0
        if mod_ok:
            self.easy_mod.setText(self.tr("health.compat_installed", count=count))
        else:
            self.easy_mod.setText(self.tr("health.compat_missing"))
        build_mismatch = False
        required = {}
        # Use scanned runtime IDs because Easy Mode also contains historical
        # player vehicles outside vehicle/car (bus/tram/truck categories).
        for resource in self.resources:
            vehicle_id = Path(resource.internal_path).stem.split(".")[0]
            if resource.domain == "vehicle" and vehicle_id in EARLY_START_CAR_PRESET:
                required[resource.resource_id] = EARLY_START_CAR_PRESET[vehicle_id]
        # AI coaches are known canonical vehicle/car resources even before a scan.
        for coach_id in ("coach_01", "coach_02", "coach_03", "coach_04", "coach_05", "coach_06"):
            required.setdefault(
                f"::/vehicle/car/{coach_id}/{coach_id}.mdl",
                EARLY_START_CAR_PRESET[coach_id],
            )
        required.update(EARLY_START_CONSTRUCTION_PRESET)
        required.update(WAREHOUSE_OVERRIDE_IDS)
        actual = {x.get("resourceId"): x.get("newYearFrom") for x in manifest.get("overrides", []) if isinstance(x, dict)}
        profile_ok = all(actual.get(k) == v for k, v in required.items())
        self.easy_profile.setText(self.tr("health.profile_ready") if profile_ok else self.tr("health.profile_missing"))
        if patch_health == "verified" and profile_ok and not build_mismatch:
            self.easy_overall.setText(self.tr("health.ready"))
            self.easy_overall.setStyleSheet("color:#6edb97;font-weight:700;font-size:13pt")
        elif state == "vanilla" and not mod_ok:
            self.easy_overall.setText(self.tr("health.vanilla"))
            self.easy_overall.setStyleSheet("color:#aeb4bf;font-weight:700;font-size:13pt")
        else:
            self.easy_overall.setText(self.tr("health.incomplete_custom"))
            self.easy_overall.setStyleSheet("color:#f0b35a;font-weight:700;font-size:13pt")
        self.refresh_primary_actions(patch_health == "verified")
        self.sync_header_status()
