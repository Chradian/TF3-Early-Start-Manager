from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QColor

from tf3_early_start_manager.models import Resource
from tf3_early_start_manager.scanner.classifier import vehicle_navigation_category

TARGET_YEAR = 1850
REFERENCE_YEAR = 1900
INTERNAL_YEAR_SENTINEL = 100000
SCAN_DOMAINS = ("vehicle", "depots", "stations", "warehouses", "infrastructure", "buildings", "industries", "assets")

class ResourceTableModel(QAbstractTableModel):
    HEADER_KEYS = ("status", "name", "source", "type", "original_from", "new_from", "original_to", "new_to")

    def __init__(self, translator, parent=None):
        super().__init__(parent)
        self._tr = translator
        self.resources: list[Resource] = []

    def set_resources(self, resources: list[Resource]) -> None:
        self.beginResetModel()
        self.resources = resources
        self.endResetModel()

    def rowCount(self, parent=None):
        parent = QModelIndex() if parent is None else parent
        return 0 if parent.isValid() else len(self.resources)
    def columnCount(self, parent=None):
        parent = QModelIndex() if parent is None else parent
        return 0 if parent.isValid() else len(self.HEADER_KEYS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self._tr(f"table.{self.HEADER_KEYS[section]}")
        return None

    @staticmethod
    def source_label(resource: Resource) -> str:
        if resource.source_type == "vanilla":
            return "Vanilla"
        prefix = "Mod.IO" if resource.source_type == "modio" else "Local"
        return f"{prefix}: {resource.source_name}"

    @staticmethod
    def year_text(resource: Resource, value: int) -> str:
        if value >= INTERNAL_YEAR_SENTINEL:
            return "Internal"
        return "∞" if value == 0 else str(value)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        r = self.resources[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.UserRole:
            return r
        if role == Qt.ItemDataRole.DisplayRole:
            values = (
                "⚙" if r.internal else ("🔒" if r.locked else ("●" if r.changed else ("⚠" if r.confidence == "analysis" else ""))),
                r.name,
                self.source_label(r),
                r.extension,
                self.year_text(r, r.year_from),
                self.year_text(r, r.new_year_from),
                self.year_text(r, r.year_to),
                self.year_text(r, r.new_year_to),
            )
            return values[col]
        if role == Qt.ItemDataRole.ToolTipRole and r.locked:
            return self._tr("tooltips.required_1850")
        if role == Qt.ItemDataRole.ForegroundRole and col == 0:
            if r.locked:
                return QColor("#d7ad58")
            if r.changed:
                return QColor("#65c97a")
        if role == Qt.ItemDataRole.TextAlignmentRole and col in (0, 4, 5, 6, 7):
            return int(Qt.AlignmentFlag.AlignCenter)
        return None

    def flags(self, index):
        flags = super().flags(index)
        if index.column() in (5, 7):
            r = self.resources[index.row()]
            if not r.locked and not r.internal and r.modifier:
                flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole or index.column() not in (5, 7):
            return False
        r = self.resources[index.row()]
        try:
            year = int(value)
        except (TypeError, ValueError):
            return False
        if r.locked or r.internal or not r.modifier:
            return False
        if index.column() == 5:
            if not TARGET_YEAR <= year <= 9999 or (r.new_year_to > 0 and year > r.new_year_to):
                return False
            r.new_year_from = year
        else:
            if not 0 <= year <= 9999 or (year > 0 and year < r.new_year_from):
                return False
            r.new_year_to = year
        self.dataChanged.emit(self.index(index.row(), 0), self.index(index.row(), 7), [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ForegroundRole])
        return True

    def notify_resources(self, resources: list[Resource]) -> None:
        rows = [self.resources.index(r) for r in resources if r in self.resources]
        for row in rows:
            left = self.index(row, 0)
            right = self.index(row, self.columnCount() - 1)
            self.dataChanged.emit(left, right, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ForegroundRole])

class ResourceFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scope = ("all", None)
        self.query = ""
        self.sources = {"vanilla", "modio", "local"}
        self.transitions_only = False
        self.changed_only = False
        self.show_all = False
        self.setDynamicSortFilter(False)

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        r = model.resources[source_row]
        scope, category = self.scope
        if scope != "all" and r.domain != scope:
            return False
        if scope in SCAN_DOMAINS and category is not None:
            if scope == "vehicle" and " / " in category:
                navigation = vehicle_navigation_category(r)
                if navigation != category and not navigation.startswith(category + " / "):
                    return False
            elif r.category != category:
                return False
        if r.source_type not in self.sources:
            return False
        if not self.show_all and r.browser_internal:
            return False
        if self.transitions_only:
            if r.internal:
                return False
            if not TARGET_YEAR <= r.year_from <= REFERENCE_YEAR:
                return False
        if self.changed_only and not r.changed:
            return False
        if self.query:
            searchable = f"{r.name} {r.resource_id} {r.internal_path} {r.domain} {r.category} {r.extension} {r.source_type} {r.source_name} {r.source_id} {r.vehicle_role} {r.power_type}".lower()
            if self.query not in searchable:
                return False
        return True

    def lessThan(self, left, right):
        lm = self.sourceModel().resources[left.row()]
        rm = self.sourceModel().resources[right.row()]
        col = left.column()
        if col == 4:
            return lm.year_from < rm.year_from
        if col == 5:
            return lm.new_year_from < rm.new_year_from
        if col == 6:
            return lm.year_to < rm.year_to
        if col == 7:
            return lm.new_year_to < rm.new_year_to
        lv = self.sourceModel().data(left, Qt.ItemDataRole.DisplayRole) or ""
        rv = self.sourceModel().data(right, Qt.ItemDataRole.DisplayRole) or ""
        return str(lv).lower() < str(rv).lower()

    def refilter_rows(self) -> None:
        self.beginFilterChange()
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
