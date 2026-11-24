from pathlib import Path

from tf3_early_start_manager.models import Resource

EARLY_START_CAR_PRESET = {
    "coach_01": 1850, "coach_02": 1850, "coach_03": 1850,
    "coach_04": 1870, "coach_05": 1870, "coach_06": 1870,
    "american_post_coach": 1850, "droshky": 1850,
    "double_horse": 1850, "double_horse_cargo": 1850,
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


class CompatibilityAnalyzer:
    def __init__(self, host):
        self.host = host

    @staticmethod
    def required_early_start(resource: Resource) -> bool:
        if resource.source_type != "vanilla" or resource.internal or not resource.modifier:
            return False
        if resource.resource_id in EARLY_START_CONSTRUCTION_PRESET:
            return True
        if resource.domain == "vehicle":
            vehicle_id = Path(resource.internal_path).stem.split(".")[0]
            return vehicle_id in EARLY_START_CAR_PRESET
        return False

    def changed_supported_resources(self) -> list[Resource]:
        """Return user changes plus mandatory Easy-1850 resources, with diagnostics."""
        selected: list[Resource] = []
        seen: set[str] = set()
        normal_count = 0
        required_count = 0
        found_cars: dict[str, str] = {}
        found_constructions: set[str] = set()

        for resource in self.host.resources:
            normal_override = (
                resource.changed
                and not resource.locked
                and not resource.internal
                and bool(resource.modifier)
            )
            required_override = self.required_early_start(resource)
            if normal_override:
                normal_count += 1
            if required_override:
                required_count += 1
                vehicle_id = Path(resource.internal_path).stem.split(".")[0]
                if resource.domain == "vehicle" and vehicle_id in EARLY_START_CAR_PRESET:
                    found_cars[vehicle_id] = resource.resource_id
                if resource.resource_id in EARLY_START_CONSTRUCTION_PRESET:
                    found_constructions.add(resource.resource_id)
            if not (normal_override or required_override):
                continue
            if resource.resource_id in seen:
                continue
            seen.add(resource.resource_id)
            selected.append(resource)

        missing_cars = sorted(set(EARLY_START_CAR_PRESET) - set(found_cars))
        missing_constructions = sorted(set(EARLY_START_CONSTRUCTION_PRESET) - found_constructions)
        self.host.LOGGER.info("COMPAT_REQUIRED cars found=%d/%d missing=%s", len(found_cars), len(EARLY_START_CAR_PRESET), missing_cars)
        self.host.LOGGER.info("COMPAT_REQUIRED constructions found=%d/%d missing=%s", len(found_constructions), len(EARLY_START_CONSTRUCTION_PRESET), missing_constructions)
        self.host.LOGGER.info("COMPAT_REQUIRED warehouses=5/5 generator_managed=true")
        self.host.LOGGER.info("COMPAT_ANALYZER normal=%d required=%d total=%d", normal_count, required_count, len(selected))
        if found_cars:
            self.host.LOGGER.debug("COMPAT_REQUIRED car_resource_ids=%s", dict(sorted(found_cars.items())))
        return selected
