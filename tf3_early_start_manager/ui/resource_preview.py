from __future__ import annotations
import os,sys,zipfile
from pathlib import Path
from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtGui import QAction, QGuiApplication, QImage, QPixmap
from PySide6.QtWidgets import QMenu,QMessageBox
from tf3_early_start_manager.models import Resource
from tf3_early_start_manager.scanner.classifier import vehicle_navigation_category
from .resource_browser import ResourceTableModel

class ResourcePreviewController:
    def __init__(self, host, app_root: Path):
        self.host = host
        self.app_root = Path(app_root)
    def __getattr__(self,name):
        return getattr(self.host,name)

    def thumbnail_cache_dir(self) -> Path:
        path = self.app_root / "cache" / "thumbnails"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def cached_thumbnail(self, resource: Resource) -> Path | None:
        if not resource.preview_file:
            return None
        import hashlib
        key = hashlib.sha1(f"{resource.zip_path}|{resource.preview_file}".encode()).hexdigest()
        jpg = self.thumbnail_cache_dir() / f"{key}.jpg"
        png = self.thumbnail_cache_dir() / f"{key}.png"
        if jpg.is_file():
            return jpg
        if png.is_file():
            return png
        try:
            if resource.zip_path.is_dir():
                raw = (resource.zip_path / resource.preview_file).read_bytes()
            else:
                with zipfile.ZipFile(resource.zip_path) as archive:
                    raw = archive.read(resource.preview_file)
        except (OSError, KeyError, zipfile.BadZipFile):
            return None
        image = QImage.fromData(raw)
        if image.isNull():
            # Some Qt installations do not ship a TGA image plugin. Pillow is
            # used only as a decoder fallback; the cache remains JPG/PNG.
            try:
                from io import BytesIO

                from PIL import Image
                pil_image = Image.open(BytesIO(raw))
                pil_image.load()
                has_pil_alpha = "A" in pil_image.getbands()
                pil_image.thumbnail((320, 180))
                target = png if has_pil_alpha else jpg
                if has_pil_alpha:
                    pil_image.save(target, format="PNG", optimize=True)
                else:
                    if pil_image.mode != "RGB":
                        pil_image = pil_image.convert("RGB")
                    pil_image.save(target, format="JPEG", quality=85, optimize=True)
                return target
            except (OSError, ValueError, ImportError):
                return None
        image = image.scaled(320, 180, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        has_alpha = image.hasAlphaChannel()
        target = png if has_alpha else jpg
        fmt = "PNG" if has_alpha else "JPG"
        quality = -1 if has_alpha else 85
        if not image.save(str(target), fmt, quality):
            return None
        return target

    def update_resource_preview(self, proxy_index: QModelIndex) -> None:
        if not proxy_index.isValid():
            return
        source_index = self.resource_proxy.mapToSource(proxy_index)
        resource = self.resource_model.resources[source_index.row()]
        cache = self.cached_thumbnail(resource)
        if cache:
            pixmap = QPixmap(str(cache))
            if not pixmap.isNull():
                self.preview_image.setPixmap(pixmap.scaled(self.preview_image.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            else:
                self.preview_image.clear(); self.preview_image.setText(self.tr("preview.no_preview"))
        else:
            self.preview_image.clear(); self.preview_image.setText(self.tr("preview.no_preview"))
        preview_source = resource.preview_file or self.tr("preview.none_detected")
        source_label = ResourceTableModel.source_label(resource)
        lock = (self.tr("preview.internal_resource") + "\n") if resource.internal else ((self.tr("preview.required_resource") + "\n") if resource.locked else "")
        template_text = ""
        vehicle_role_text = self.tr("preview.vehicle_role", role=resource.vehicle_role.title()) + "\n" if resource.vehicle_role else ""
        power_type_text = self.tr("preview.power_type", power=resource.power_type.title()) + "\n" if resource.power_type in {"steam", "diesel", "electric"} or vehicle_navigation_category(resource).startswith("Rail / Trains / Other") else ""
        if resource.template_timeline:
            timeline = ", ".join(f"{a}→{'∞' if b == 0 else b}" for a, b in resource.template_timeline)
            template_text = self.tr("preview.construction_templates", timeline=timeline) + "\n"
        self.preview_text.setText(
            f"{lock}{resource.name}\n{self.tr('preview.source')}: {source_label}\n{self.tr('preview.type')}: {resource.domain} / {resource.category}\n"
            f"{self.tr('preview.original')}: {self.display_year(resource, resource.year_from)}–{'∞' if resource.year_to == 0 else self.display_year(resource, resource.year_to)}   {self.tr('preview.current')}: {self.display_year(resource, resource.new_year_from)}–{'∞' if resource.new_year_to == 0 else self.display_year(resource, resource.new_year_to)}\n"
            f"{self.tr('preview.modifier')}: {resource.modifier or self.tr('preview.analysis_only')} ({resource.confidence})\n{vehicle_role_text}{power_type_text}{template_text}"
            f"{self.tr('preview.primary')}: {resource.primary_file or resource.internal_path}\n{self.tr('preview.preview_source')}: {preview_source}\n"
            f"{self.tr('preview.related_resources')}: {len(resource.related_files)}\n{resource.runtime_resource_id}"
        )
        self.preview_description.setPlainText(resource.mod_description or self.tr("content.no_description"))

    def resource_at_view_position(self, position) -> Resource | None:
        proxy_index = self.resource_table.indexAt(position)
        if not proxy_index.isValid():
            return None
        source_index = self.resource_proxy.mapToSource(proxy_index)
        if not source_index.isValid():
            return None
        return self.resource_model.resources[source_index.row()]

    @staticmethod
    def resource_filesystem_target(resource: Resource) -> tuple[Path, bool]:
        """Return (path, is_concrete_file). Archive resources resolve to the archive."""
        container = resource.zip_path
        if container.is_file():
            return container, True
        candidate = container / Path(resource.internal_path)
        if candidate.exists():
            return candidate, candidate.is_file()
        return container, False

    @staticmethod
    def explorer_select(path: Path) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Explorer integration is currently available on Windows only.")
        resolved = path.resolve()
        if resolved.is_file():
            os.spawnl(os.P_NOWAIT, r"C:\Windows\explorer.exe", "explorer.exe", "/select,", str(resolved))
        else:
            os.startfile(resolved)

    @staticmethod
    def copy_text(text: str) -> None:
        QGuiApplication.clipboard().setText(text)

    def open_resource_context_menu(self, position) -> None:
        resource = self.resource_at_view_position(position)
        if resource is None:
            return
        menu = QMenu(self.resource_table)
        open_location = QAction(self.tr("context.open_file_location"), menu)
        open_source = QAction(self.tr("context.open_source_folder"), menu)
        copy_path = QAction(self.tr("context.copy_file_path"), menu)
        copy_id = QAction(self.tr("context.copy_resource_id"), menu)
        menu.addAction(open_location)
        menu.addAction(open_source)
        menu.addSeparator()
        menu.addAction(copy_path)
        menu.addAction(copy_id)

        target, concrete = self.resource_filesystem_target(resource)
        if not target.exists():
            open_location.setEnabled(False)
        open_location.setToolTip(
            self.tr("tooltips.select_resource_file") if concrete and resource.zip_path.is_dir()
            else self.tr("tooltips.select_archive")
        )

        def show_location() -> None:
            try:
                self.explorer_select(target)
            except (OSError, RuntimeError) as exc:
                QMessageBox.warning(self, self.tr("dialogs.open_file_location_title"), str(exc))

        def show_source() -> None:
            source = resource.zip_path if resource.zip_path.is_dir() else resource.zip_path.parent
            try:
                if not source.exists():
                    raise RuntimeError(f"Source folder no longer exists: {source}")
                if sys.platform != "win32":
                    raise RuntimeError("Explorer integration is currently available on Windows only.")
                os.startfile(source.resolve())
            except (OSError, RuntimeError) as exc:
                QMessageBox.warning(self, self.tr("dialogs.open_source_folder_title"), str(exc))

        display_path = (
            str(target)
            if resource.zip_path.is_dir()
            else f"{resource.zip_path} :: {resource.internal_path}"
        )
        open_location.triggered.connect(show_location)
        open_source.triggered.connect(show_source)
        copy_path.triggered.connect(lambda: self.copy_text(display_path))
        copy_id.triggered.connect(lambda: self.copy_text(resource.resource_id))
        menu.exec(self.resource_table.viewport().mapToGlobal(position))
