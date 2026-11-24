from __future__ import annotations

import ctypes
import json
import logging
import os
from pathlib import Path


LOGGER = logging.getLogger("tf3_early_start_manager")

LANGUAGE_ALIASES = {
    "de-de": "de", "de_at": "de", "de-at": "de", "german": "de",
    "en-us": "en", "en_us": "en", "en-gb": "en", "en_gb": "en", "english": "en",
    "es-es": "es", "spanish": "es", "fr-fr": "fr", "french": "fr",
    "it-it": "it", "italian": "it", "ja-jp": "ja", "japanese": "ja",
    "ko-kr": "ko", "korean": "ko", "nl-nl": "nl", "dutch": "nl",
    "pl-pl": "pl", "polish": "pl", "pt-br": "pt_BR", "pt_br": "pt_BR",
    "ru-ru": "ru", "russian": "ru", "zh-cn": "zh_CN", "zh_cn": "zh_CN",
    "zh-tw": "zh_TW", "zh_tw": "zh_TW",
}


def canonical_language(value: str | None) -> str:
    raw = str(value or "en").strip()
    if not raw:
        return "en"
    normalized = raw.replace(" ", "").replace(".", "-")
    lower = normalized.lower()
    if lower in LANGUAGE_ALIASES:
        return LANGUAGE_ALIASES[lower]
    base = lower.split("-", 1)[0].split("_", 1)[0]
    return LANGUAGE_ALIASES.get(base, base if base else "en")


SUPPORTED_UI_LANGUAGES = {"de", "en", "es", "fr", "it", "nl", "pl", "pt_BR", "ru"}

def windows_ui_language() -> str:
    """Return the supported Windows UI language, falling back to English."""
    if os.name != "nt":
        return "en"
    try:
        kernel32 = ctypes.windll.kernel32
        locale_name = None
        if hasattr(kernel32, "GetUserDefaultLocaleName"):
            buffer = ctypes.create_unicode_buffer(85)
            if kernel32.GetUserDefaultLocaleName(buffer, len(buffer)):
                locale_name = buffer.value
        if not locale_name:
            lcid = kernel32.GetUserDefaultUILanguage()
            locale_name = {
                0x0407: "de-DE", 0x0409: "en-US", 0x0809: "en-GB",
                0x0C0A: "es-ES", 0x040C: "fr-FR", 0x0410: "it-IT",
                0x0413: "nl-NL", 0x0415: "pl-PL", 0x0416: "pt-BR",
                0x0419: "ru-RU",
            }.get(int(lcid), "en")
        detected = canonical_language(locale_name)
        result = detected if detected in SUPPORTED_UI_LANGUAGES else "en"
        LOGGER.info("LOCALE Windows UI language raw=%s resolved=%s", locale_name, result)
        return result
    except (OSError, AttributeError, TypeError, ValueError) as exc:
        LOGGER.warning("LOCALE Windows UI language detection failed: %s", exc)
        return "en"


def initial_ui_language(settings) -> str:
    """Use a saved choice; only detect Windows language on the first run."""
    saved = settings.value("ui_language", None)
    if saved is not None and str(saved).strip():
        resolved = canonical_language(str(saved))
        return resolved if resolved in SUPPORTED_UI_LANGUAGES else "en"
    detected = windows_ui_language()
    settings.setValue("ui_language", detected)
    settings.sync()
    return detected


class LanguageResolver:
    """Central language resolution for manager UI, Vanilla and mods.

    Policy: requested language -> English -> explicit raw/default -> stable identifier.
    It never falls back to an unrelated available language.
    """

    def __init__(self, language: str, locale_root: Path | None = None) -> None:
        self.language = canonical_language(language)
        self.locale_root = locale_root or Path(__file__).resolve().parent / "languages"
        self.catalogs: dict[str, dict] = {}
        self.reload()
        self.validation_report = self.validate_catalogs()

    def reload(self) -> None:
        self.catalogs = {}
        if not self.locale_root.is_dir():
            LOGGER.error("LOCALE languages directory is missing: %s", self.locale_root)
            return
        for code in ("en", self.language):
            path = self.locale_root / f"{code}.json"
            if not path.is_file():
                continue
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                LOGGER.warning("LOCALE invalid file=%s error=%s", path, exc)
                continue
            if isinstance(value, dict):
                self.catalogs[code] = value
        if "en" not in self.catalogs:
            LOGGER.warning("LOCALE English master catalog is missing in %s", self.locale_root)

    def set_language(self, language: str) -> None:
        self.language = canonical_language(language)
        self.reload()

    @staticmethod
    def _leaf_keys(catalog: dict, prefix: str = "") -> set[str]:
        keys: set[str] = set()
        for name, value in catalog.items():
            key = f"{prefix}.{name}" if prefix else str(name)
            if isinstance(value, dict):
                keys.update(LanguageResolver._leaf_keys(value, key))
            else:
                keys.add(key)
        return keys

    def validate_catalogs(self) -> dict[str, dict[str, list[str]]]:
        """Validate every locale against en.json, which is the master key set."""
        report: dict[str, dict[str, list[str]]] = {}
        master = self.catalogs.get("en", {})
        master_keys = self._leaf_keys(master)
        if not master_keys:
            LOGGER.error("LOCALE validation unavailable: English master catalog is empty or missing")
            return report
        for code, catalog in sorted(self.catalogs.items()):
            if code == "en":
                continue
            keys = self._leaf_keys(catalog)
            missing = sorted(master_keys - keys)
            extra = sorted(keys - master_keys)
            empty = sorted(
                key for key in master_keys & keys
                if not isinstance(self._nested(catalog, key), str) or not self._nested(catalog, key).strip()
            )
            report[code] = {"missing": missing, "extra": extra, "empty": empty}
            if missing or empty or extra:
                LOGGER.warning(
                    "LOCALE validation language=%s master=%d present=%d missing=%d empty=%d extra=%d",
                    code, len(master_keys), len(keys), len(missing), len(empty), len(extra),
                )
                for key in missing:
                    LOGGER.warning("LOCALE missing catalog key language=%s key=%s", code, key)
                for key in empty:
                    LOGGER.warning("LOCALE empty catalog value language=%s key=%s", code, key)
                for key in extra:
                    LOGGER.info("LOCALE extra catalog key language=%s key=%s", code, key)
            else:
                LOGGER.info("LOCALE validation language=%s complete=%d/%d", code, len(master_keys), len(master_keys))
        return report

    @staticmethod
    def _nested(catalog: dict, key: str):
        current = catalog
        for part in key.split("."):
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
        return current

    def ui(self, key: str, **values) -> str:
        text = None
        for code in (self.language, "en"):
            candidate = self._nested(self.catalogs.get(code, {}), key)
            if isinstance(candidate, str) and candidate.strip():
                text = candidate
                break
        if text is None:
            LOGGER.warning("LOCALE missing UI key=%s language=%s", key, self.language)
            text = key
        try:
            return text.format(**values)
        except (KeyError, ValueError):
            LOGGER.warning("LOCALE format error key=%s values=%s", key, values)
            return text

    @staticmethod
    def language_keys(language: str) -> tuple[str, ...]:
        code = canonical_language(language)
        aliases = {
            "de": ("de", "de_DE", "de-DE", "german"),
            "en": ("en", "en_US", "en-US", "en_GB", "english"),
            "pt_BR": ("pt_BR", "pt-BR", "pt"),
            "zh_CN": ("zh_CN", "zh-CN", "zh_Hans"),
            "zh_TW": ("zh_TW", "zh-TW", "zh_Hant"),
        }
        return aliases.get(code, (code, code.replace("_", "-")))

    def content(self, values, *, raw: str = "", identifier: str = "") -> str:
        """Resolve localized content without choosing an unrelated language."""
        if isinstance(values, str) and values.strip():
            return values.strip()
        if isinstance(values, dict):
            for code in (self.language, "en"):
                for key in self.language_keys(code):
                    value = values.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        return identifier

    def catalog_value(self, catalog: dict, key: str, *, raw: str = "", identifier: str = "") -> str:
        if not isinstance(catalog, dict):
            return raw.strip() if raw.strip() else identifier
        candidates: dict[str, str] = {}
        for language, strings in catalog.items():
            if isinstance(strings, dict):
                value = strings.get(key)
                if isinstance(value, str) and value.strip():
                    candidates[canonical_language(str(language))] = value.strip()
        return self.content(candidates, raw=raw, identifier=identifier)


