"""Transport Fever 3 installation model."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Installation:
    root: Path
    distribution: str = "Custom"

    @property
    def content(self) -> Path:
        return self.root / "base" / "content"

    @property
    def gui_zip(self) -> Path:
        return self.content / "gui.zip"
