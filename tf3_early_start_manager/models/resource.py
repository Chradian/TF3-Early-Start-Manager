"""Scanned TF3 resource model."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Resource:
    name: str
    resource_id: str
    domain: str
    category: str
    extension: str
    modifier: str | None
    confidence: str
    zip_path: Path
    internal_path: str
    year_from: int
    year_to: int
    new_year_from: int
    new_year_to: int
    metadata_car: bool = False
    carrier: str = ""
    locked: bool = False
    group_key: str = ""
    primary_file: str = ""
    related_files: tuple[str, ...] = ()
    preview_file: str | None = None
    internal: bool = False
    template_timeline: tuple[tuple[int, int], ...] = ()
    template_based: bool = False
    source_type: str = "vanilla"
    source_name: str = "Vanilla"
    source_id: str = ""
    vehicle_role: str = ""
    power_type: str = ""
    mod_description: str = ""
    source_namespace: str = ""

    @property
    def runtime_resource_id(self) -> str:
        if self.source_type == "vanilla" or not self.source_namespace:
            return self.resource_id
        return f"{self.source_namespace}{self.resource_id}"

    @property
    def changed(self) -> bool:
        return self.new_year_from != self.year_from or self.new_year_to != self.year_to

    @property
    def browser_internal(self) -> bool:
        """Technical/support resource hidden by the default browser view."""
        if self.domain == "vehicle" and self.extension == ".mdl":
            return self.vehicle_role in {"support", "group"}
        return (
            not self.locked
            and not self.template_based
            and self.year_from == 0
            and self.year_to == 0
        )

    def available(self, year: int) -> bool:
        if self.year_from > 0 and year < self.year_from:
            return False
        return not (self.year_to > 0 and year > self.year_to)
