"""Localization services."""
from .resolver import LANGUAGE_ALIASES, SUPPORTED_UI_LANGUAGES, LanguageResolver, canonical_language, initial_ui_language, windows_ui_language
__all__ = ["LANGUAGE_ALIASES", "SUPPORTED_UI_LANGUAGES", "LanguageResolver", "canonical_language", "initial_ui_language", "windows_ui_language"]
