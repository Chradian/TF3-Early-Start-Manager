from __future__ import annotations
import logging
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidgetItem
from tf3_early_start_manager.scanner.classifier import vehicle_navigation_category
LOGGER=logging.getLogger("tf3_early_start_manager")
SCAN_DOMAINS=("vehicle","depots","stations","warehouses","infrastructure","buildings","industries","assets")

class ResourceTreeController:
    def __init__(self, host):
        self.host=host
    def __getattr__(self,name):
        return getattr(self.host,name)

    def select_all_resources(self) -> None:
        for index in range(self.resource_tree.topLevelItemCount()):
            item = self.resource_tree.topLevelItem(index)
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data[0] == "all":
                self.resource_tree.blockSignals(True)
                self.resource_tree.setCurrentItem(item)
                self.resource_tree.blockSignals(False)
                return

    def toggle_resource_tree_expansion(self) -> None:
        if self.resource_tree_expanded:
            self.resource_tree.collapseAll()
            self.resource_tree_expanded = False
            self.tree_toggle_button.setText(self.tr("actions.expand_all"))
            self.tree_toggle_button.setToolTip(self.tr("tooltips.expand_all_resources"))
        else:
            self.resource_tree.expandAll()
            self.resource_tree_expanded = True
            self.tree_toggle_button.setText(self.tr("actions.collapse_all"))
            self.tree_toggle_button.setToolTip(self.tr("tooltips.collapse_all_resources"))

    def _rebuild_tree_categories(self) -> None:
        def category_label(raw: str) -> str:
            key = raw.strip().lower().replace(" ", "_")
            return self.tr(f"categories.{key}")

        label_map = {domain: category_label(domain) for domain in SCAN_DOMAINS}
        for i in range(self.resource_tree.topLevelItemCount()):
            root = self.resource_tree.topLevelItem(i)
            data = root.data(0, Qt.ItemDataRole.UserRole)
            if not data or data[0] not in SCAN_DOMAINS:
                continue
            domain = data[0]
            show_all = (
                self.show_all_resources.isChecked()
                if hasattr(self, "show_all_resources")
                else False
            )

            domain_resources = [
                r
                for r in self.resources
                if r.domain == domain
                and (
                    show_all
                    or not r.browser_internal
                )
            ]
            root.setText(0, f"{label_map[domain]} ({len(domain_resources)})")
            root.takeChildren()
            if domain == "vehicle":
                navigation_counts: dict[tuple[str, ...], int] = {}
                for resource in domain_resources:
                    path = tuple(vehicle_navigation_category(resource).split(" / "))
                    navigation_counts[path] = navigation_counts.get(path, 0) + 1

                def add_navigation_level(
                    parent_item: QTreeWidgetItem,
                    prefix: tuple[str, ...],
                    counts: dict[tuple[str, ...], int] = navigation_counts,
                    current_domain: str = domain,
                ) -> None:
                    names = sorted(
                        {
                            path[len(prefix)]
                            for path in counts
                            if len(path) > len(prefix)
                            and path[:len(prefix)] == prefix
                        },
                        key=str.lower,
                    )

                    for name in names:
                        full = (*prefix, name)

                        count = sum(
                            value
                            for path, value in counts.items()
                            if path[:len(full)] == full
                        )

                        item = QTreeWidgetItem(
                            [f"{category_label(name)} ({count})"]
                        )

                        item.setData(
                            0,
                            Qt.ItemDataRole.UserRole,
                            (
                                current_domain,
                                " / ".join(full),
                            ),
                        )

                        parent_item.addChild(item)

                        add_navigation_level(
                            item,
                            full,
                            counts,
                            current_domain,
                        )

                add_navigation_level(root, ())
            else:
                for cat in sorted({r.category for r in domain_resources}, key=str.lower):
                    count = sum(r.category == cat for r in domain_resources)
                    child = QTreeWidgetItem([f"{category_label(cat)} ({count})"])
                    child.setData(0, Qt.ItemDataRole.UserRole, (domain, cat))
                    root.addChild(child)
        self.resource_tree.collapseAll()
        self.resource_tree_expanded = False
        if hasattr(self, "tree_toggle_button"):
            self.tree_toggle_button.setText(self.tr("actions.expand_all"))
            self.tree_toggle_button.setToolTip(self.tr("tooltips.expand_all_resources"))
        counts = {t: sum(r.source_type == t for r in self.resources) for t in ("vanilla", "modio", "local")}
        LOGGER.info("SOURCE_COUNTS vanilla=%d modio=%d local=%d", counts["vanilla"], counts["modio"], counts["local"])

    def selected_scope(self) -> tuple[str, str | None]:
        items = self.resource_tree.selectedItems()
        if not items:
            return ("all", None)
        data = items[0].data(0, Qt.ItemDataRole.UserRole)
        return data or ("all", None)

    def active_source_types(self) -> set[str]:
        selected = set()
        if self.source_vanilla.isChecked(): selected.add("vanilla")
        if self.source_modio.isChecked(): selected.add("modio")
        if self.source_local.isChecked(): selected.add("local")
        if not selected:
            # Keep at least Vanilla active, avoiding an accidentally empty browser.
            self.source_vanilla.blockSignals(True)
            self.source_vanilla.setChecked(True)
            self.source_vanilla.blockSignals(False)
            selected.add("vanilla")
        all_checked = len(selected) == 3
        if hasattr(self, "source_all"):
            self.source_all.blockSignals(True)
            self.source_all.setChecked(all_checked)
            self.source_all.blockSignals(False)
        return selected
