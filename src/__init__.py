"""Upload Assistant common initialisation.

Importing :mod:`src` activates global patches that ensure files created by
the application use Unraid-friendly ownership and permissions.
"""

from .file_permissions import patch_file_permissions

patch_file_permissions()

__all__ = ["patch_file_permissions"]

