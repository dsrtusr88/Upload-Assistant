"""Helpers for Upload Assistant naming logic."""
from __future__ import annotations

import os

from typing import Any, Iterable

try:  # pragma: no cover - optional dependency during testing
    from src.radarr import sceneNaming as _radarr_scene_naming
except Exception:  # noqa: BLE001 - fallback when Radarr deps are unavailable
    _radarr_scene_naming = None


def _extract_radarr_scene_name(radarr_data: dict[str, Any] | None) -> str | None:
    """Return the scene name from Radarr data when available."""

    if _radarr_scene_naming is not None:
        scene_name = _radarr_scene_naming(radarr_data)
        if scene_name:
            return scene_name

    movie_file = (radarr_data or {}).get("movieFile") or {}
    scene_name = movie_file.get("sceneName")

    if isinstance(scene_name, str):
        scene_name = scene_name.strip()
        if scene_name:
            return scene_name

    return None


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


def _append_original_extension(original_name: Any, new_name: str) -> str:
    """Append the original file extension to ``new_name`` when appropriate."""

    if not isinstance(original_name, str):
        return new_name

    _, ext = os.path.splitext(original_name.strip())
    if ext and not new_name.lower().endswith(ext.lower()):
        return f"{new_name}{ext}"

    return new_name


def apply_preferred_scene_name(meta: dict[str, Any], config: dict[str, Any]) -> None:
    """Override ``meta['name']`` with Radarr's ``sceneName`` when configured."""
    try:
        naming = (config or {}).get("NAMING", {})
        if not naming.get("prefer_radarr_scene_name", False):
            return

        radarr_data = meta.get("radarr") or {}
        scene_name = _extract_radarr_scene_name(radarr_data)
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
            meta["name"] = _append_original_extension(meta.get("name"), scene_name)
            meta.setdefault("torrent_name_override", meta["name"])
    except Exception:
        # Never break the upload flow due to naming issues
        pass


def prefer_radarr_scene_name(meta: dict[str, Any]) -> None:
    """Unconditionally prefer Radarr's ``sceneName`` for ``meta['name']`` when present."""

    try:
        radarr_data = meta.get("radarr") or {}
        scene_name = _extract_radarr_scene_name(radarr_data)
        if not scene_name:
            return

        if scene_name:
            meta["name"] = _append_original_extension(meta.get("name"), scene_name)
            meta.setdefault("torrent_name_override", meta["name"])
    except Exception:
        # Naming issues should never interrupt the main workflow
        pass


__all__ = [
    "apply_preferred_scene_name",
    "prefer_radarr_scene_name",
]
