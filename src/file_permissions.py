"""Utilities for enforcing Unraid-friendly file permissions.

This module centralises logic for ensuring that any files or directories
created by the application are owned by the ``nobody`` user and have
``777`` permissions.  The behaviour is implemented by monkey patching a
handful of common file-creation helpers (``open``, ``os.makedirs`` and
friends) so that the desired permissions are applied automatically after
the underlying operation succeeds.

While Unraid uses the ``nobody`` user and ``users`` group, those
principals may not exist in every execution environment (e.g. during
local development or within CI containers).  The helper gracefully falls
back to the executing user's primary group if ``users`` is not
available, and it safely ignores any permission errors that may occur
when the process lacks the ability to change ownership or mode.

The module exposes a single ``patch_file_permissions`` function which is
called during package initialisation (see ``src/__init__.py``).  Importing
``src`` anywhere in the codebase therefore activates the behaviour once
for the lifetime of the process.
"""

from __future__ import annotations

import asyncio
import builtins
import logging
import os
import shutil
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

try:  # pragma: no cover - platform specific modules
    import grp
    import pwd
except ImportError:  # pragma: no cover - Windows fallback
    grp = None  # type: ignore
    pwd = None  # type: ignore

_LOGGER = logging.getLogger(__name__)

_PATCHED = False
_ORIGINAL_OPEN = builtins.open
_ORIGINAL_MAKEDIRS = os.makedirs
_ORIGINAL_MKDIR = os.mkdir
_ORIGINAL_PATH_WRITE_TEXT = Path.write_text
_ORIGINAL_PATH_WRITE_BYTES = Path.write_bytes
_ORIGINAL_PATH_MKDIR = Path.mkdir

_DEFAULT_ROOT = Path(__file__).resolve().parent.parent

_ENV_ROOTS = os.environ.get("UNRAID_PERMISSION_ROOTS")
if _ENV_ROOTS:
    _PERMISSION_ROOTS = [Path(p).expanduser().resolve(strict=False) for p in _ENV_ROOTS.split(os.pathsep) if p]
else:
    single_root = os.environ.get("UNRAID_PERMISSION_ROOT", str(_DEFAULT_ROOT))
    _PERMISSION_ROOTS = [Path(single_root).expanduser().resolve(strict=False)]


def _is_managed_path(path: os.PathLike[str] | str) -> bool:
    try:
        resolved = Path(path).expanduser().resolve(strict=False)
    except Exception:  # pragma: no cover - invalid paths are ignored
        return False

    for root in _PERMISSION_ROOTS:
        try:
            if resolved == root or resolved.is_relative_to(root):
                return True
        except AttributeError:  # pragma: no cover - Python < 3.9 fallback
            root_str = str(root)
            resolved_str = str(resolved)
            if resolved_str == root_str or resolved_str.startswith(root_str.rstrip(os.sep) + os.sep):
                return True
    return False


try:  # ``aiofiles`` is optional at runtime.
    import aiofiles  # type: ignore

    _ORIGINAL_AIOFILES_OPEN = aiofiles.open  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - imported lazily in production
    aiofiles = None  # type: ignore
    _ORIGINAL_AIOFILES_OPEN = None

WRITE_FLAGS = {"w", "a", "x", "+"}


def _should_apply(mode: str) -> bool:
    """Return ``True`` if ``mode`` may modify a file."""

    return any(flag in mode for flag in WRITE_FLAGS)


def _resolve_target_group(user: str, desired_group: str | None) -> Optional[str]:
    """Best-effort resolution of the group used for chown operations."""

    if desired_group is None or grp is None or pwd is None:
        return desired_group

    try:
        grp.getgrnam(desired_group)
        return desired_group
    except KeyError:
        pass

    try:
        user_info = pwd.getpwnam(user)
        primary_group = grp.getgrgid(user_info.pw_gid).gr_name
        return primary_group
    except (KeyError, AttributeError):
        return None


def _ensure_permissions(path: os.PathLike[str] | str) -> None:
    """Apply Unraid-friendly permissions to ``path``.

    The function ignores missing files and any permission related errors.
    """

    if not path:
        return

    target = os.fspath(path)
    if not os.path.exists(target):
        return

    if not _is_managed_path(target):
        return

    target_user = os.environ.get("UNRAID_TARGET_USER", "nobody")
    requested_group = os.environ.get("UNRAID_TARGET_GROUP", "users")
    target_group = _resolve_target_group(target_user, requested_group)

    try:
        os.chmod(target, 0o777)
    except Exception as exc:  # pragma: no cover - environment specific
        _LOGGER.debug("Unable to chmod %s: %s", target, exc)

    try:
        shutil.chown(target, user=target_user, group=target_group)
    except Exception as exc:  # pragma: no cover - environment specific
        _LOGGER.debug("Unable to chown %s: %s", target, exc)


async def _async_ensure_permissions(path: os.PathLike[str] | str) -> None:
    """Async wrapper to run ``_ensure_permissions`` in a worker thread."""

    await asyncio.to_thread(_ensure_permissions, path)


def _collect_missing_dirs(path: os.PathLike[str] | str) -> Iterable[str]:
    """Identify directory levels that do not yet exist before creation."""

    missing: list[str] = []
    current = os.path.abspath(os.fspath(path))
    while current and not os.path.exists(current):
        if not _is_managed_path(current):
            break
        missing.append(current)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return missing


class _PermissionAwareFile:
    """Wrap file objects to ensure permissions once closed."""

    def __init__(self, file_obj: Any, path: os.PathLike[str] | str):
        self._file = file_obj
        self._path = path
        self._ensured = False

    def _ensure(self) -> None:
        if not self._ensured:
            _ensure_permissions(self._path)
            self._ensured = True

    def __getattr__(self, name: str) -> Any:  # pragma: no cover - delegation
        return getattr(self._file, name)

    def __enter__(self):  # pragma: no cover - context manager delegation
        self._file.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):  # pragma: no cover - context manager
        result = self._file.__exit__(exc_type, exc, tb)
        self._ensure()
        return result

    def close(self) -> None:  # pragma: no cover - simple delegation
        self._file.close()
        self._ensure()

    def __iter__(self):  # pragma: no cover - iteration support
        return iter(self._file)


class _AsyncPermissionAwareFile:
    """Async equivalent of ``_PermissionAwareFile``."""

    def __init__(self, file_obj: Any, path: os.PathLike[str] | str):
        self._ctx_manager = file_obj
        self._path = path
        self._ensured = False
        self._handle: Any = None

    async def _ensure(self) -> None:
        if not self._ensured:
            await _async_ensure_permissions(self._path)
            self._ensured = True

    def __getattr__(self, name: str) -> Any:  # pragma: no cover - delegation
        target = self._handle if self._handle is not None else self._ctx_manager
        return getattr(target, name)

    async def __aenter__(self):  # pragma: no cover - context manager
        self._handle = await self._ctx_manager.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb):  # pragma: no cover
        result = await self._ctx_manager.__aexit__(exc_type, exc, tb)
        await self._ensure()
        self._handle = None
        return result

    async def close(self) -> None:  # pragma: no cover - delegation
        target = self._handle if self._handle is not None else self._ctx_manager
        close_method = getattr(target, "close", None)
        if close_method is None:
            return
        result = close_method()
        if asyncio.iscoroutine(result):
            await result
        await self._ensure()


def _patch_open() -> None:
    def wrapped_open(  # type: ignore[override]
        file: os.PathLike[str] | str,
        mode: str = "r",
        buffering: int = -1,
        encoding: Optional[str] = None,
        errors: Optional[str] = None,
        newline: Optional[str] = None,
        closefd: bool = True,
        opener: Optional[Callable[..., Any]] = None,
    ):
        handle = _ORIGINAL_OPEN(
            file,
            mode,
            buffering,
            encoding,
            errors,
            newline,
            closefd,
            opener,
        )
        if _should_apply(mode):
            return _PermissionAwareFile(handle, file)
        return handle

    builtins.open = wrapped_open  # type: ignore[assignment]


def _patch_aiofiles() -> None:
    if aiofiles is None or _ORIGINAL_AIOFILES_OPEN is None:
        return

    def wrapped_aiofiles_open(*args: Any, **kwargs: Any):
        mode = "r"
        if len(args) >= 2:
            mode = args[1]
        elif "mode" in kwargs:
            mode = kwargs["mode"]

        handle = _ORIGINAL_AIOFILES_OPEN(*args, **kwargs)
        if _should_apply(mode):
            return _AsyncPermissionAwareFile(handle, args[0] if args else kwargs.get("file"))
        return handle

    aiofiles.open = wrapped_aiofiles_open  # type: ignore[attr-defined]


def _patch_os_makedirs() -> None:
    @wraps(_ORIGINAL_MAKEDIRS)
    def wrapped_makedirs(name: os.PathLike[str] | str, mode: int = 0o777, exist_ok: bool = False):
        missing = list(_collect_missing_dirs(name))
        result = _ORIGINAL_MAKEDIRS(name, mode=mode, exist_ok=exist_ok)
        for path in missing:
            _ensure_permissions(path)
        _ensure_permissions(name)
        return result

    os.makedirs = wrapped_makedirs  # type: ignore[assignment]


def _patch_os_mkdir() -> None:
    @wraps(_ORIGINAL_MKDIR)
    def wrapped_mkdir(path: os.PathLike[str] | str, mode: int = 0o777):
        missing = list(_collect_missing_dirs(path))
        result = _ORIGINAL_MKDIR(path, mode)
        for directory in missing:
            _ensure_permissions(directory)
        _ensure_permissions(path)
        return result

    os.mkdir = wrapped_mkdir  # type: ignore[assignment]


def _patch_path_methods() -> None:
    def wrapped_write_text(self: Path, data: str, *args: Any, **kwargs: Any):
        result = _ORIGINAL_PATH_WRITE_TEXT(self, data, *args, **kwargs)
        _ensure_permissions(self)
        return result

    def wrapped_write_bytes(self: Path, data: bytes, *args: Any, **kwargs: Any):
        result = _ORIGINAL_PATH_WRITE_BYTES(self, data, *args, **kwargs)
        _ensure_permissions(self)
        return result

    def wrapped_path_mkdir(self: Path, mode: int = 0o777, parents: bool = False, exist_ok: bool = False):
        manage_target = _is_managed_path(self)
        missing: Iterable[str] = []
        if parents and manage_target:
            missing = _collect_missing_dirs(self)
        result = _ORIGINAL_PATH_MKDIR(self, mode=mode, parents=parents, exist_ok=exist_ok)
        if parents and manage_target:
            for directory in missing:
                _ensure_permissions(directory)
        if manage_target:
            _ensure_permissions(self)
        return result

    Path.write_text = wrapped_write_text  # type: ignore[assignment]
    Path.write_bytes = wrapped_write_bytes  # type: ignore[assignment]
    Path.mkdir = wrapped_path_mkdir  # type: ignore[assignment]


def patch_file_permissions() -> None:
    """Activate all file-permission patches once per interpreter."""

    global _PATCHED
    if _PATCHED:
        return

    _patch_open()
    _patch_os_makedirs()
    _patch_os_mkdir()
    _patch_path_methods()
    _patch_aiofiles()

    _PATCHED = True
