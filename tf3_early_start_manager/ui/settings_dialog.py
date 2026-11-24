from __future__ import annotations
from tf3_early_start_manager.version import APP_NAME, APP_VERSION
import json,logging,os,shutil,subprocess,sys
from pathlib import Path
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QApplication,QComboBox,QDialog,QFileDialog,QFormLayout,QFrame,QHBoxLayout,QLabel,QLineEdit,QMessageBox,QProgressBar,QPushButton,QVBoxLayout,QWidget
from tf3_early_start_manager.models import Installation
from tf3_early_start_manager.localization import canonical_language
from tf3_early_start_manager.scanner import SCAN_CACHE_SCHEMA_VERSION
TARGET_YEAR=1850
LOGGER=logging.getLogger("tf3_early_start_manager")

class SettingsDialogController:
    def __init__(self,host,app_root:Path,log_dir:Path,log_file:Path):
        object.__setattr__(self,"host",host);object.__setattr__(self,"app_root",Path(app_root));object.__setattr__(self,"log_dir",Path(log_dir));object.__setattr__(self,"log_file",Path(log_file))
    def __getattr__(self,name):
        if name=="LOG_DIR": return self.log_dir
        if name=="LOG_FILE": return self.log_file
        return getattr(self.host,name)
    def __setattr__(self,name,value):
        if name in {"host","app_root","log_dir","log_file"}: object.__setattr__(self,name,value)
        else: setattr(self.host,name,value)

    def open_settings(self) -> None:
        d = QDialog(self.host)
        d.setWindowTitle(self.tr("actions.settings"))
        root = QVBoxLayout(d)
        form = QFormLayout()
        start = QComboBox()
        start.addItem(self.tr("actions.easy_mode"), "easy")
        start.addItem(self.tr("actions.advanced_mode"), "advanced")
        start.setCurrentIndex(1 if self.settings.value("start_mode", "easy") == "advanced" else 0)
        lang = QComboBox()
        language_options = (
            ("Deutsch", "de"),
            ("English", "en"),
            ("Español", "es"),
            ("Français", "fr"),
            ("Italiano", "it"),
            ("Nederlands", "nl"),
            ("Polski", "pl"),
            ("Português (Brasil)", "pt_BR"),
            ("Русский", "ru"),
        )
        current_index = 0
        for index, (label, code) in enumerate(language_options):
            lang.addItem(label, code)
            if self.language == code:
                current_index = index
        lang.setCurrentIndex(current_index)
        path = QLineEdit(str(self.installation.root) if self.installation else str(self.settings.value("game_path", "")))
        path_status = QLabel()
        browse = QPushButton(self.tr("actions.browse"))
        path_row = QWidget()
        pr = QHBoxLayout(path_row)
        pr.setContentsMargins(0, 0, 0, 0)
        pr.addWidget(path, 1)
        pr.addWidget(browse)
        form.addRow(self.tr("settings.start_screen"), start)
        form.addRow(self.tr("settings.language"), lang)
        form.addRow(self.tr("settings.tf3_installation"), path_row)
        form.addRow(self.tr("settings.path_check"), path_status)
        root.addLayout(form)

        cache_box = QFrame()
        cache_box.setObjectName("panel")
        cache_layout = QVBoxLayout(cache_box)
        cache_title = QLabel(self.tr("sections.cache"))
        cache_title.setObjectName("section")
        cache_status = QLabel()
        cache_status.setWordWrap(True)
        cache_buttons = QHBoxLayout()
        clear_scan_button = QPushButton(self.tr("settings.clear_scan_cache"))
        clear_thumbs_button = QPushButton(self.tr("settings.clear_thumbnail_cache"))
        clear_all_button = QPushButton(self.tr("settings.clear_all_caches"))
        cache_buttons.addWidget(clear_scan_button)
        cache_buttons.addWidget(clear_thumbs_button)
        cache_buttons.addWidget(clear_all_button)
        cache_buttons.addStretch()
        cache_layout.addWidget(cache_title)
        cache_layout.addWidget(cache_status)
        cache_layout.addLayout(cache_buttons)
        root.addWidget(cache_box)

        log_box = QFrame()
        log_box.setObjectName("panel")
        log_layout = QVBoxLayout(log_box)
        log_title = QLabel(self.tr("sections.log"))
        log_title.setObjectName("section")
        log_buttons = QHBoxLayout()
        open_log_button = QPushButton(self.tr("settings.open_log"))
        open_log_dir_button = QPushButton(self.tr("settings.open_log_folder"))
        export_diag_button = QPushButton(self.tr("settings.export_diagnostics"))
        log_buttons.addWidget(open_log_button)
        log_buttons.addWidget(open_log_dir_button)
        log_buttons.addWidget(export_diag_button)
        log_buttons.addStretch()
        log_layout.addWidget(log_title)
        log_layout.addLayout(log_buttons)
        root.addWidget(log_box)

        def open_log() -> None:
            try:
                if sys.platform == "win32":
                    os.startfile(self.log_file)
            except OSError as exc:
                QMessageBox.warning(d, self.tr("dialogs.log_title"), str(exc))

        def open_log_dir() -> None:
            try:
                if sys.platform == "win32":
                    os.startfile(self.log_dir)
            except OSError as exc:
                QMessageBox.warning(d, self.tr("dialogs.log_title"), str(exc))

        open_log_button.clicked.connect(open_log)
        open_log_dir_button.clicked.connect(open_log_dir)
        def export_diagnostics() -> None:
            target, _ = QFileDialog.getSaveFileName(d, "Export Diagnostics", str(Path.home() / "tf3_early_start_diagnostics.txt"), "Text files (*.txt)")
            if not target:
                return
            manifest = self.installed_manifest()
            archives, resource_count, cache_bytes = self.scan_cache_summary()
            patch_health, patch_detail = self.patch_health()
            exe_fingerprint = self.tf3_executable_fingerprint()
            report = [
                f"{APP_NAME} {APP_VERSION}", f"Cache schema: {SCAN_CACHE_SCHEMA_VERSION}",
                f"Target year: {TARGET_YEAR}", f"Mode: {'Advanced' if self.mode_stack.currentIndex() else 'Easy'}",
                f"TF3 detected: {bool(self.installation)}", f"GUI state: {self.gui_state() if self.installation else 'unavailable'}",
                f"Patch health: {patch_health}", f"Patch detail: {patch_detail}",
                f"Patch generation: {self.load_patch_state().get('currentGeneration', 0)}",
                f"Patch history entries: {len(self.load_patch_state().get('history', []))}",
                f"TF3 executable: {json.dumps(exe_fingerprint, ensure_ascii=False)}",
                f"Compatibility overrides: {len(manifest.get('overrides', []))}",
                f"Resources: {resource_count}", f"Cache archives: {archives}", f"Cache bytes: {cache_bytes}",
                f"Log: {self.log_file.name}",
            ]
            Path(target).write_text("\n".join(report) + "\n", encoding="utf-8")
        export_diag_button.clicked.connect(export_diagnostics)

        def refresh_cache_status() -> None:
            archives, resources, scan_bytes = self.scan_cache_summary()
            thumb_dir = self.app_root / "cache" / "thumbnails"
            thumbs = [f for f in thumb_dir.glob("*") if f.is_file()] if thumb_dir.is_dir() else []
            thumb_bytes = sum(f.stat().st_size for f in thumbs)
            cache_status.setText(self.tr(
                "cache.status",
                archives=archives,
                resources=resources,
                scan_kb=f"{scan_bytes / 1024:.1f}",
                thumbnails=len(thumbs),
                thumb_mb=f"{thumb_bytes / (1024 * 1024):.1f}",
            ))

        def clear_scan_action() -> None:
            self.clear_scan_cache()
            self.resources = []
            self._rebuild_tree_categories()
            self.resource_model.set_resources([])
            self.apply_resource_filter()
            refresh_cache_status()

        def clear_thumb_action() -> None:
            thumb_dir = self.app_root / "cache" / "thumbnails"
            if thumb_dir.is_dir():
                shutil.rmtree(thumb_dir)
            refresh_cache_status()

        def clear_all_action() -> None:
            clear_scan_action()
            clear_thumb_action()

        clear_scan_button.clicked.connect(clear_scan_action)
        clear_thumbs_button.clicked.connect(clear_thumb_action)
        clear_all_button.clicked.connect(clear_all_action)
        refresh_cache_status()

        def validate() -> Installation | None:
            inst = self.validate_installation(Path(path.text().strip()))
            path_status.setText(f"✓ {inst.root}" if inst else self.tr("status.invalid_tf3_installation"))
            path_status.setStyleSheet("color:#6edb97" if inst else "color:#df6b6b")
            return inst

        def choose() -> None:
            value = QFileDialog.getExistingDirectory(d, "Select Transport Fever 3", path.text() or str(Path.home()))
            if value:
                path.setText(value)
                validate()

        def save() -> None:
            inst = validate()
            if not inst:
                QMessageBox.warning(d, self.tr("dialogs.invalid_path_title"), self.tr("dialogs.invalid_tf3_path"))
                return
            previous_root = self.installation.root if self.installation else None
            installation_changed = previous_root != inst.root
            self.installation = inst
            self.installations.installation = inst
            if installation_changed:
                self.invalidate_health_cache("installation-changed")
            previous_language = self.language
            selected_language = canonical_language(str(lang.currentData()))
            selected_mode = str(start.currentData())
            self.settings.setValue("game_path", str(inst.root))
            self.settings.setValue("game_distribution", inst.distribution)
            self.settings.setValue("ui_language", selected_language)
            self.settings.setValue("start_mode", selected_mode)
            self.settings.sync()
            d.accept()

            if selected_language != previous_language:
                LOGGER.info("LOCALE language changed old=%s new=%s; restarting UI", previous_language, selected_language)
                restart = QDialog(self.host)
                restart.setWindowTitle(self.tr("language.restart_title"))
                restart.setModal(True)
                restart.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
                restart_layout = QVBoxLayout(restart)
                restart_label = QLabel(self.tr("language.restarting"))
                restart_label.setObjectName("section")
                restart_progress = QProgressBar()
                restart_progress.setRange(0, 0)
                restart_layout.addWidget(restart_label)
                restart_layout.addWidget(restart_progress)
                restart.setFixedWidth(420)
                restart.show()
                def launch_restarted_manager() -> None:
                    try:
                        command = ([sys.executable, "--language-restart"] if getattr(sys, "frozen", False) else [sys.executable, str(self.app_root / "main_v1.0.0.py"), "--language-restart"])
                        subprocess.Popen(command, cwd=str(self.app_root), close_fds=True)
                    except OSError as exc:
                        LOGGER.error("LOCALE restart failed: %s", exc)
                        restart.reject()
                        QMessageBox.information(self.host, self.tr("language.restart_title"), self.tr("language.restart_manual"))
                        return
                    QApplication.quit()
                QTimer.singleShot(350, launch_restarted_manager)
                return
            self.language = selected_language
            self.i18n.set_language(self.language)
            if installation_changed:
                LOGGER.info("SETTINGS installation changed old=%s new=%s; reloading cached content", previous_root, inst.root)
                self.resources = []
                self.resource_model.set_resources([])
                self.load_tf3_translations()
                self.load_cached_resources_on_startup()
                self.refresh_all_status()
            else:
                LOGGER.info("SETTINGS saved without installation/language change; scan skipped")
            if selected_mode == "advanced":
                self.show_advanced_mode()
            else:
                self.show_easy_mode()

        browse.clicked.connect(choose)
        path.textChanged.connect(lambda _: validate())
        buttons = QHBoxLayout()
        buttons.addStretch()
        save_btn = QPushButton(self.tr("actions.save"))
        save_btn.setObjectName("primary")
        close_btn = QPushButton(self.tr("actions.close"))
        save_btn.clicked.connect(save)
        close_btn.clicked.connect(d.reject)
        buttons.addWidget(save_btn)
        buttons.addWidget(close_btn)
        root.addLayout(buttons)
        validate()
        d.exec()
