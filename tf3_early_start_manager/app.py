"""Application bootstrap for TF3 Early Start Manager."""
from __future__ import annotations

import ctypes
import sys

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from tf3_early_start_manager.localization import LanguageResolver, initial_ui_language
from tf3_early_start_manager.paths import RESOURCE_ROOT
from tf3_early_start_manager.ui.main_window import MainWindow
from tf3_early_start_manager.version import APP_NAME


def run() -> int:
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "TF3EarlyStartManager.1.0"
        )

    app = QApplication(sys.argv)

    icon_path = RESOURCE_ROOT / "assets" / "TF3_Early_Start_Manager.ico"
    app.setWindowIcon(QIcon(str(icon_path)))

def run(argv: list[str] | None = None) -> int:
    """Create the Qt application, show MainWindow and return the Qt exit code."""
    args = sys.argv if argv is None else argv
    app = QApplication(args)
    app.setApplicationName(APP_NAME)

    language_restart = "--language-restart" in args
    splash = None
    if language_restart:
        settings = QSettings("TF3EarlyStartManager", "TF3EarlyStartManager")
        language = initial_ui_language(settings)
        resolver = LanguageResolver(language, RESOURCE_ROOT / "languages")
        canvas = QPixmap(520, 120)
        canvas.fill(QColor("#22262c"))
        splash = QSplashScreen(canvas)
        splash.showMessage(
            resolver.ui("language.applying"),
            Qt.AlignmentFlag.AlignCenter,
            QColor("#e8ebef"),
        )
        splash.show()
        app.processEvents()

    window = MainWindow()
    window.show()
    if splash is not None:
        splash.finish(window)
    if language_restart and not window.load_scan_cache():
        QTimer.singleShot(100, window.scan_content)
    return app.exec()
