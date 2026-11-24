from __future__ import annotations
import logging
import time
from pathlib import Path
from PySide6.QtWidgets import QMessageBox
from tf3_early_start_manager.models import Resource
LOGGER = logging.getLogger("tf3_early_start_manager")
TARGET_YEAR=1850
EARLY_START_CAR_PRESET={"coach_01":1850,"coach_02":1850,"coach_03":1850,"coach_04":1870,"coach_05":1870,"coach_06":1870,"american_post_coach":1850,"droshky":1850,"double_horse":1850,"double_horse_cargo":1850}
EARLY_START_CONSTRUCTION_PRESET={"::/depots/rail/rail_depot.con.lua":1850,"::/depots/rail/rail_maint_station.con.lua":1850,"::/depots/road/road_depot/road_depot.con.lua":1850,"::/depots/road/road_maint_station.con.lua":1850,"::/depots/road/tram_depot/tram_depot.con.lua":1850,"::/depots/water/water_depot.con.lua":1850,"::/depots/water/water_maint_station.con.lua":1850,"::/stations/rail/modular_station/modular_station.con.lua":1850,"::/stations/street/modular_street_station/modular_terminal.con.lua":1850}

class ResourceSelectionController:
    def __init__(self, host):
        self.host=host
    def __getattr__(self,name):
        return getattr(self.host,name)

    def visible_resource_count(self) -> int:
        return self.resource_proxy.rowCount()

    def update_resource_count(self) -> None:
        self.resource_count.setText(self.tr("status.visible_resources", visible=self.visible_resource_count(), total=len(self.resources)))

    def _set_proxy_values(self) -> None:
        self.resource_proxy.scope = self.selected_scope()
        self.resource_proxy.query = self.search.text().strip().lower()
        self.resource_proxy.sources = self.active_source_types()
        self.resource_proxy.transitions_only = self.transitions_only.isChecked()
        self.resource_proxy.changed_only = self.changed_only.isChecked()
        self.resource_proxy.show_all = self.show_all_resources.isChecked()

    def apply_resource_filter(self) -> None:
        if not hasattr(self,"resource_proxy"): return
        self._set_proxy_values(); self.resource_proxy.refilter_rows(); self.update_overview_or_count()

    def update_overview_or_count(self) -> None:
        self.update_resource_count()

    def selected_resource_objects(self) -> list[Resource]:
        result: list[Resource] = []
        for proxy_index in self.resource_table.selectionModel().selectedRows():
            source_index = self.resource_proxy.mapToSource(proxy_index)
            resource = self.resource_model.resources[source_index.row()]
            if resource not in result:
                result.append(resource)
        return result

    def _finish_resource_batch_update(self, resources: list[Resource]) -> None:
        self.preview_image.clear()
        self.preview_image.setText(self.tr("preview.no_preview"))
        self.preview_text.setText(self.tr("preview.hover_hint"))
        self.preview_description.clear()
        self.resource_model.notify_resources(resources)
        self.resource_proxy.refilter_rows()
        self.update_overview_or_count()

    def set_selected_year(self) -> None:
        selected = self.selected_resource_objects()
        if not selected:
            return
        if not self.change_from.isChecked() and not self.change_to.isChecked():
            QMessageBox.information(self, self.tr("dialogs.timeline_title"), self.tr("dialogs.select_timeline_bounds"))
            return
        year, until = self.year_spin.value(), self.until_spin.value()
        if self.change_from.isChecked() and self.change_to.isChecked() and until > 0 and until < year:
            QMessageBox.warning(self, self.tr("dialogs.timeline_title"), self.tr("dialogs.invalid_timeline_bounds"))
            return
        changed = []
        for resource in selected:
            if resource.locked or resource.internal or not resource.modifier:
                continue
            candidate_from = year if self.change_from.isChecked() else resource.new_year_from
            candidate_to = until if self.change_to.isChecked() else resource.new_year_to
            if candidate_to > 0 and candidate_to < candidate_from:
                continue
            resource.new_year_from = candidate_from
            resource.new_year_to = candidate_to
            changed.append(resource)
        self._finish_resource_batch_update(changed)

    def reset_selected(self) -> None:
        started = time.perf_counter()
        selected = self.selected_resource_objects()
        LOGGER.info("RESET_SELECTED start rows=%d", len(selected))
        if not selected:
            return
        changed: list[Resource] = []
        for resource in selected:
            if resource.internal:
                LOGGER.debug("RESET skip internal %s", resource.resource_id)
                continue
            old = resource.new_year_from
            if resource.locked:
                vehicle_id = Path(resource.internal_path).stem.split(".")[0]
                resource.new_year_from = EARLY_START_CONSTRUCTION_PRESET.get(
                    resource.resource_id,
                    EARLY_START_CAR_PRESET.get(vehicle_id, resource.year_from),
                )
            else:
                resource.new_year_from = resource.year_from
            resource.new_year_to = resource.year_to
            changed.append(resource)
            LOGGER.debug("RESET %s %s -> %s", resource.resource_id, old, resource.new_year_from)
        LOGGER.info("RESET_SELECTED model update complete changed=%d", len(changed))
        self._finish_resource_batch_update(changed)
        LOGGER.info("RESET_SELECTED finished %.3fs", time.perf_counter() - started)
