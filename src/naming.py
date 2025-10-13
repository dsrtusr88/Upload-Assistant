"""Helpers for Upload Assistant naming logic."""
from __future__ import annotations

from typing import Any, Iterable

DEFAULT_STRIP_CHARS: tuple[str, ...] = ("{", "}", "[", "]", "(", ")")
DEFAULT_SPACE_REPLACEMENT = "."


def _apply_scene_token_normalization(scene_name: str) -> str:
    """Apply lightweight token normalization for scene names."""
    replacements = {
        "DD+": "DDP",
        "HDR.": "HDR10.",
    }
    for old, new in replacements.items():
        scene_name = scene_name.replace(old, new)
    return scene_name


def _sanitize_scene_name(
    scene_name: str,
    *,
    replacement: str | None = DEFAULT_SPACE_REPLACEMENT,
    strip_chars: Iterable[str] | None = DEFAULT_STRIP_CHARS,
) -> str:
    """Sanitize a scene name using configured characters and space replacement."""
    if strip_chars:
        for char in strip_chars:
            if isinstance(char, str) and char:
                scene_name = scene_name.replace(char, "")
    if replacement is not None:
        scene_name = scene_name.replace(" ", replacement)
    return scene_name


def apply_preferred_scene_name(meta: dict[str, Any], config: dict[str, Any]) -> None:
    """Override ``meta['name']`` with Radarr's ``sceneName`` when configured."""
    try:
        naming = (config or {}).get("NAMING", {})
        if not naming.get("prefer_radarr_scene_name", False):
            return

        radarr_data = meta.get("radarr") or {}
        movie_file = radarr_data.get("movieFile") or {}
        scene_name = movie_file.get("sceneName")
        if not scene_name:
            return

        scene_name = str(scene_name).strip()
        if not scene_name:
            return

        if naming.get("normalize_scene_tokens", False):
            scene_name = _apply_scene_token_normalization(scene_name)

        if naming.get("sanitize_filenames", True):
            replacement = naming.get("space_replacement", DEFAULT_SPACE_REPLACEMENT)
            if not isinstance(replacement, str):
                replacement = DEFAULT_SPACE_REPLACEMENT

            strip_chars_config = naming.get("strip_chars", DEFAULT_STRIP_CHARS)
            if isinstance(strip_chars_config, (list, tuple, set)):
                strip_chars = tuple(
                    char for char in strip_chars_config if isinstance(char, str) and char
                )
            elif isinstance(strip_chars_config, str):
                stripped = strip_chars_config.strip()
                if "," in stripped:
                    # Allow comma-separated characters/strings (e.g. "{,}")
                    parsed = [
                        item.strip()
                        for item in stripped.split(",")
                        if item.strip()
                    ]
                else:
                    # Fall back to treating each non-whitespace character individually
                    parsed = [char for char in stripped if not char.isspace()]

                strip_chars = tuple(parsed) if parsed else DEFAULT_STRIP_CHARS
            else:
                strip_chars = DEFAULT_STRIP_CHARS

            scene_name = _sanitize_scene_name(
                scene_name,
                replacement=replacement,
                strip_chars=strip_chars,
            )

        if scene_name:
            meta["name"] = scene_name
    except Exception:
        # Never break the upload flow due to naming issues
        pass


def prefer_radarr_scene_name(meta: dict[str, Any]) -> None:
    """Unconditionally prefer Radarr's ``sceneName`` for ``meta['name']`` when present."""

    try:
        radarr_data = meta.get("radarr") or {}
        movie_file = radarr_data.get("movieFile") or {}
        scene_name = (movie_file.get("sceneName") or "").strip()
        if not scene_name:
            return

        scene_name = scene_name.replace("DD+", "DDP")
        scene_name = scene_name.replace("HDR.", "HDR10.")

        for char in ("{", "}", "[", "]", "(", ")"):
            scene_name = scene_name.replace(char, "")

        if scene_name:
            meta["name"] = scene_name
    except Exception:
        # Naming issues should never interrupt the main workflow
        pass


__all__ = [
    "apply_preferred_scene_name",
    "prefer_radarr_scene_name",
]
