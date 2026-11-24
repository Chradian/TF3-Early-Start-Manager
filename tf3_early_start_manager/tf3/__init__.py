"""TF3 installation discovery and launching."""
from .discovery import InstallationService
from .launcher import start_game
__all__ = ["InstallationService", "start_game"]

from .patch_state import PatchService as PatchStateService
from .gui_patch import PatchService as GuiPatchService
