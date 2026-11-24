from __future__ import annotations
from tf3_early_start_manager.version import APP_VERSION

import json
import logging
import os
import re
import shutil
import tempfile
import time
import zipfile
from collections.abc import Iterable
from pathlib import Path

from tf3_early_start_manager.models import Resource

LOGGER = logging.getLogger("tf3_early_start_manager")
LOGGER = logging.getLogger("tf3_early_start_manager")
TARGET_YEAR = 1850
COMPATIBILITY_MOD_ID = "tf3_early_start_compatibility"
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

class CompatibilityGenerator:
    def __init__(self, host, app_root: Path):
        self.host = host
        self.app_root = Path(app_root)
    def __getattr__(self, name):
        return getattr(self.host, name)

    def generate_compatibility_mod(self, resources: Iterable[Resource]) -> Path:
        resources = list(resources)
        if not resources and not WAREHOUSE_ERA_A_OVERRIDES:
            raise RuntimeError("No supported runtime overrides are configured.")
        output = self.app_root / "generated_compatibility_mod"
        if output.exists():
            shutil.rmtree(output)
        (output / "content").mkdir(parents=True)
        (output / "_metadata").mkdir()
        warehouse_dir = output / "content" / "warehouses"
        warehouse_dir.mkdir(parents=True)

        # Warehouse MetaConstructions inherit the compatibility-mod namespace.
        # Use the current Vanilla script as a bridge, but make every resource path
        # returned by it explicit so models, ground textures, sounds and the final
        # construction continue to resolve from Vanilla.
        assert self.installation
        warehouse_zip = self.installation.content / "warehouses.zip"
        try:
            with zipfile.ZipFile(warehouse_zip) as archive:
                warehouse_script = self.scanner.decode(archive.read("warehouses/warehouse.script.lua"))
        except (OSError, KeyError, zipfile.BadZipFile) as exc:
            raise RuntimeError(f"Could not read Vanilla warehouse.script.lua: {exc}") from exc
        if not warehouse_script:
            raise RuntimeError("Vanilla warehouse.script.lua is empty or unreadable.")

        replacements = (
            ('"warehouse.con"', '"::/warehouses/warehouse.con"'),
            ("'warehouse.con'", "'::/warehouses/warehouse.con'"),
            ('"entrance/', '"::/warehouses/entrance/'),
            ("'entrance/", "'::/warehouses/entrance/"),
            ('"sound/', '"::/warehouses/sound/'),
            ("'sound/", "'::/warehouses/sound/"),
            ('"icons/', '"::/warehouses/icons/'),
            ("'icons/", "'::/warehouses/icons/"),
            ('"wh_', '"::/warehouses/wh_'),
            ("'wh_", "'::/warehouses/wh_"),
            ('"/industries/', '"::/industries/'),
            ("'/industries/", "'::/industries/"),
        )
        for old, new in replacements:
            warehouse_script = warehouse_script.replace(old, new)

        # warehouse.script.lua executes inside the compatibility-mod namespace.
        # Rewrite Vanilla root imports so TF3 does not search content/scripts in
        # tf3_early_start_compatibility.
        warehouse_script = warehouse_script.replace(
            'require "/scripts/', 'require "::/scripts/'
        ).replace(
            "require '/scripts/", "require '::/scripts/"
        ).replace(
            'require("/scripts/', 'require("::/scripts/'
        ).replace(
            "require('/scripts/", "require('::/scripts/"
        )
        # warehouse.script.lua also imports entrance helpers relative to itself.
        warehouse_script = warehouse_script.replace(
            'require "entrance/', 'require "::/warehouses/entrance/'
        ).replace(
            "require 'entrance/", "require '::/warehouses/entrance/"
        ).replace(
            'require("entrance/', 'require("::/warehouses/entrance/'
        ).replace(
            "require('entrance/", "require('::/warehouses/entrance/"
        )

        unresolved = (
            'require "/scripts/', "require '/scripts/",
            'require("/scripts/', "require('/scripts/",
            'require "entrance/', "require 'entrance/",
            'require("entrance/', "require('entrance/",
        )
        remaining = [token for token in unresolved if token in warehouse_script]
        if remaining:
            raise RuntimeError(
                "Warehouse script still contains unresolved Vanilla imports: "
                + ", ".join(remaining)
            )

        # Validate only references that are literal in warehouse.script.lua.
        # wh_* and sound/* paths are assembled dynamically at runtime and therefore
        # cannot be validated by checking for a static rewritten marker here.
        if "::/warehouses/warehouse.con" not in warehouse_script:
            raise RuntimeError(
                "Expected namespace-safe Warehouse construction reference was not generated."
            )
        (warehouse_dir / "warehouse.script.lua").write_text(warehouse_script, encoding="utf-8")
        LOGGER.info("WAREHOUSE_OVERRIDE generated namespace-safe warehouse.script.lua bridge")

        for filename, cargo_type in WAREHOUSE_ERA_A_OVERRIDES.items():
            lower = cargo_type.lower()
            warehouse_source = (
                "-- Generated by TF3 Early Start Manager 0.9.42\n"
                "-- Era A warehouse template: vanilla logic, availability starts at 1850.\n"
                'local warehouse = ug_require "::/warehouses/warehouse.tl"\n'
                f'local template = warehouse.makeTemplate("{cargo_type}", {TARGET_YEAR}, warehouse.eraBStart)\n'
                "-- makeTemplate() uses paths relative to the loading resource. This file\n"
                "-- lives in the compatibility mod, so point them back to vanilla.\n"
                'template.createTemplateScript.fileName = "warehouse.script@createTemplateFn"\n'
                f'template.createTemplateScript.params.initialModule = "::/warehouses/wh_{lower}.module"\n'
                f'template.description.icon = "::/warehouses/icons/wh_{lower}.tga"\n'
                f'template.description.previewIcon = "::/warehouses/icons/wh_{lower}_preview.tga"\n'
                "return template\n"
            )
            (warehouse_dir / filename).write_text(warehouse_source, encoding="utf-8")
            LOGGER.info("WAREHOUSE_OVERRIDE generated %s %s->eraBStart", filename, TARGET_YEAR)

        grouped: dict[str, dict[str, tuple[int, int]]] = {}
        for r in resources:
            assert r.modifier
            grouped.setdefault(r.modifier, {})[r.runtime_resource_id] = (r.new_year_from, r.new_year_to)

        patch_state = self.load_patch_state()
        patch_generation = int(patch_state.get("currentGeneration", 0) or 0)
        build_info = self.tf3_build_info()
        expected_tf3_build = str(build_info.get("build") or "").strip()
        if not expected_tf3_build:
            expected_tf3_build = str(patch_state.get("tf3Build") or "").strip()
        LOGGER.info(
            "COMPAT_BUILD expected=%s source=%s",
            expected_tf3_build or "unknown",
            "exe" if build_info.get("build") else "patch-state",
        )
        compatibility_format = 16
        lines = [
            "-- Generated by TF3 Early Start Manager 0.9.42",
            f'local MANAGER_VERSION = "{APP_VERSION}"',
            f"local PATCH_GENERATION = {patch_generation}",
            f"local COMPATIBILITY_FORMAT = {compatibility_format}",
        ]
        if expected_tf3_build:
            lines.append(f'local EXPECTED_TF3_BUILD = "{expected_tf3_build}"')
        else:
            lines.append("local EXPECTED_TF3_BUILD = nil")
        lines.append("local overrides = {")
        for modifier, values in sorted(grouped.items()):
            lines.append(f'    ["{modifier}"] = {{')
            for rid, years in sorted(values.items()):
                lines.append(f'        ["{rid}"] = {{ from = {years[0]}, to = {years[1]} }},')
            lines.append("    },")
        lines += [
            "}",
            "",
            "local function makeModifier(modifierName)",
            "    return function(fileName, data)",
            "        local years = overrides[modifierName][fileName]",
            "        if years == nil then return data end",
            "        local year = years.from",
            "        local yearTo = years.to",
            "        if modifierName == 'loadConstruction' and data.constructionTemplates ~= nil then",
            "            local changed = 0",
            "            for _, template in ipairs(data.constructionTemplates) do",
            "                if template.availability ~= nil and template.availability.yearFrom == 1900 then",
            "                    template.availability.yearFrom = year",
            "                    changed = changed + 1",
            "                end",
            "            end",
            '            log.message("TF3 Early Start: loadConstruction " .. tostring(fileName) .. " Era-A templates 1900 -> " .. tostring(year) .. " (" .. tostring(changed) .. " changed)")',
            "        elseif data.availability ~= nil then",
            "            local old = data.availability.yearFrom",
            "            data.availability.yearFrom = year",
            "            data.availability.yearTo = yearTo",
            '            log.message("TF3 Early Start: " .. modifierName .. " " .. tostring(fileName) .. " availability -> " .. tostring(year) .. "-" .. tostring(yearTo))',
            "        elseif data.metadata ~= nil and data.metadata.availability ~= nil then",
            "            local old = data.metadata.availability.yearFrom",
            "            data.metadata.availability.yearFrom = year",
            "            data.metadata.availability.yearTo = yearTo",
            '            log.message("TF3 Early Start: " .. modifierName .. " " .. tostring(fileName) .. " availability -> " .. tostring(year) .. "-" .. tostring(yearTo))',
            "        else",
            '            log.warning("TF3 Early Start: target has no availability: " .. tostring(fileName))',
            "        end",
            "        return data",
            "    end",
            "end",
            "",
            "local function runFn(_config, _params)",
        ]
        for modifier in sorted(grouped):
            lines.append(f'    addModifier("{modifier}", makeModifier("{modifier}"))')
        lines += ["end", "", "function data()", "    return { runFn = runFn }", "end", ""]
        version_state = {
            "managerVersion": APP_VERSION,
            "patchGeneration": patch_generation,
            "compatibilityFormat": compatibility_format,
            "expectedTf3Build": expected_tf3_build or None,
            "tf3BuildInfo": build_info,
            "tf3Executable": patch_state.get("tf3Executable", {}),
            "patchedGuiSha256": patch_state.get("patchedSha256", ""),
        }
        (output / "early_start_version.json").write_text(
            json.dumps(version_state, indent=2), encoding="utf-8"
        )
        warning_res = (
            'function data()\n'
            '    return { type = "notification", data = { guiType = "Caution", label = "TF3 Early Start Update Warning", initiallyIgnoredType = false } }\n'
            'end\n'
        )
        (output / "content" / "early_start_build_warning.res.lua").write_text(warning_res, encoding="utf-8")
        warning_script = (
            'local function useDataState(params, _simParams)\n'
            '    return { title = "TF3 Early Start needs verification", description = "Transport Fever 3 changed from build " .. tostring(params.expectedBuild) .. " to build " .. tostring(params.runningBuild) .. ". Close the game and run TF3 Early Start Manager.", icon = "::/game_mechanics/notifications/gui/icons/terminal_full.tga" }\n'
            'end\n'
            'function data()\n'
            '    return { useDataState = useDataState }\n'
            'end\n'
        )
        (output / "content" / "early_start_build_warning.script.lua").write_text(warning_script, encoding="utf-8")
        health_dir = output / "content" / "gui" / "early_start"
        health_dir.mkdir(parents=True, exist_ok=True)
        health_res = (
            'function data()\n'
            '    return {\n'
            '        type = "react-replacement-config",\n'
            '        data = {\n'
            '            filePath = "tf3_early_start_compatibility::/gui/early_start/build_health.script",\n'
            '            doReplaceFn = "doReplaceFn",\n'
            '            order = 1000,\n'
            '        },\n'
            '    }\n'
            'end\n'
        )
        (health_dir / "build_health.res.lua").write_text(health_res, encoding="utf-8")
        expected_lua = f'"{expected_tf3_build}"' if expected_tf3_build else "nil"
        health_lines = [
            f"local EXPECTED_TF3_BUILD = {expected_lua}",
            f'local MANAGER_VERSION = "{APP_VERSION}"',
            f"local PATCH_GENERATION = {patch_generation}",
            "local executed = false",
            "",
            "local function showBuildWarning(expectedBuild, currentBuild)",
            "    log.warning('TF3 Early Start needs verification: expected build ' .. tostring(expectedBuild) .. ', running build ' .. tostring(currentBuild))",
            "    if api == nil or api.cmd == nil then return end",
            "    pcall(function()",
            "        api.cmd.sendCommand(api.cmd.makeScriptingSendEventCmd('', 'Notifications', 'add', {",
            "            type = resolve('tf3_early_start_compatibility::/early_start_build_warning.script'),",
            "            params = { expectedBuild = tostring(expectedBuild), runningBuild = tostring(currentBuild) },",
            "            autoDismissDuration = 30000,",
            "        }))",
            "    end)",
            "end",
            "",
            "local function doReplaceFn(_replacementApi)",
            "    if executed then return end",
            "    executed = true",
            "    local currentBuild = nil",
            "    if type(getBuildVersion) == 'function' then",
            "        local ok, value = pcall(getBuildVersion)",
            "        if ok and value ~= nil then currentBuild = tostring(value) end",
            "    end",
            '    log.message("TF3 Early Start Health: manager=" .. MANAGER_VERSION .. " generation=" .. tostring(PATCH_GENERATION) .. " expectedBuild=" .. tostring(EXPECTED_TF3_BUILD) .. " runtimeBuild=" .. tostring(currentBuild))',
            "    if EXPECTED_TF3_BUILD ~= nil and currentBuild ~= nil and tostring(EXPECTED_TF3_BUILD) ~= currentBuild then",
            "        showBuildWarning(EXPECTED_TF3_BUILD, currentBuild)",
            "    end",
            "end",
            "",
            "function data()",
            "    return { doReplaceFn = doReplaceFn }",
            "end",
            "",
        ]
        (health_dir / "build_health.script.lua").write_text("\n".join(health_lines), encoding="utf-8")
        (output / "content" / "mod.script.lua").write_text("\n".join(lines), encoding="utf-8")

        mod_json = {"modId": COMPATIBILITY_MOD_ID, "revision": 1, "severityAdd": "Warning", "severityRemove": "Warning", "visible": True, "cosmetic": False, "runScript": {"fileName": f"{COMPATIBILITY_MOD_ID}::mod.script@runFn"}}
        (output / "mod.json").write_text(json.dumps(mod_json, indent=2), encoding="utf-8")
        (output / "_metadata" / "modinfo.json").write_text(json.dumps({"name": "TF3 Early Start Compatibility", "summary": "Runtime availability overrides generated by TF3 Early Start Manager 0.9.42", "authors": [{"name": "TF3 Early Start Manager", "role": "CREATOR"}], "tags": ["Script Mod"]}, indent=2), encoding="utf-8")
        runtime_manifest = [{"resourceId": r.resource_id, "runtimeResourceId": r.runtime_resource_id, "sourceNamespace": r.source_namespace, "domain": r.domain, "category": r.category, "type": r.extension, "modifier": r.modifier, "originalYearFrom": r.year_from, "newYearFrom": r.new_year_from, "originalYearTo": r.year_to, "newYearTo": r.new_year_to, "locked": r.locked, "templateBased": r.template_based, "templateTimeline": [list(pair) for pair in r.template_timeline], "sourceType": r.source_type, "sourceName": r.source_name, "sourceId": r.source_id} for r in resources]
        warehouse_manifest = [
            {
                "resourceId": resource_id,
                "domain": "warehouses",
                "category": "Era A",
                "type": ".metacon.tl",
                "modifier": "resourceOverride",
                "originalYearFrom": 1900,
                "newYearFrom": year,
                "locked": True,
                "templateBased": True,
                "templateTimeline": [[1900, 1940]],
                "sourceType": "vanilla",
                "sourceName": "Vanilla",
                "sourceId": "",
            }
            for resource_id, year in sorted(WAREHOUSE_OVERRIDE_IDS.items())
        ]
        manifest = {
            "generatorVersion": APP_VERSION,
            "compatibilityFormat": compatibility_format,
            "patchGeneration": patch_generation,
            "runtimeHealthMode": "exe-build-vs-runtime-build",
            "runtimeVersionResource": "gui/early_start/build_health.script.lua",
            "visibleUpdateWarning": True,
            "expectedTf3Build": expected_tf3_build,
            "targetStartYear": TARGET_YEAR,
            "overrides": runtime_manifest + warehouse_manifest,
        }
        (output / "overrides.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return output
