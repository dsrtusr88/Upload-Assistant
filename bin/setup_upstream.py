#!/usr/bin/env python3
"""Utility to add and fetch the official Upload Assistant upstream remote.

This small helper makes it easy for fork maintainers to align with the
primary repository maintained by Audionut. By default it:

* Adds a remote named ``upstream`` that points to Audionut's repository
  (if it doesn't already exist).
* Ensures the remote URL matches the expected value.
* Fetches the remote so new branches and tags are available locally.
* Optionally configures the current branch to track a selected upstream branch.

Example usage::

    python bin/setup_upstream.py --track-branch master

The script is safe to run multiple times – it will not recreate an existing
remote nor overwrite a remote that points elsewhere.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Optional

DEFAULT_REMOTE_NAME = "upstream"
DEFAULT_REMOTE_URL = "https://github.com/Audionut/Upload-Assistant.git"


class GitCommandError(RuntimeError):
    """Raised when an underlying git command fails."""


def run_git_command(*args: str, capture_output: bool = False) -> subprocess.CompletedProcess:
    """Run a git command and return the completed process.

    Args:
        *args: Individual arguments passed to ``git``. For example,
            ``run_git_command("status", "--short")`` executes
            ``git status --short``.
        capture_output: When ``True``, stdout/stderr are captured and
            returned on the ``CompletedProcess`` instance. When ``False``,
            the command inherits the parent's stdout/stderr.

    Returns:
        The :class:`subprocess.CompletedProcess` describing the execution.

    Raises:
        GitCommandError: If ``git`` exits with a non-zero status.
    """

    kwargs: dict[str, object] = {
        "check": False,
        "text": True,
    }
    if capture_output:
        kwargs.update({"stdout": subprocess.PIPE, "stderr": subprocess.PIPE})

    result = subprocess.run(["git", *args], **kwargs)
    if result.returncode != 0:
        raise GitCommandError(
            f"git {' '.join(args)} failed with exit code {result.returncode}.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result


def ensure_git_repository() -> None:
    """Ensure the current working directory is inside a git repository."""

    try:
        run_git_command("rev-parse", "--is-inside-work-tree", capture_output=True)
    except GitCommandError as exc:  # pragma: no cover - defensive guard
        raise SystemExit("This script must be run from within a git repository.") from exc


def ensure_remote(remote_name: str, remote_url: str) -> bool:
    """Ensure the desired remote exists and matches the expected URL.

    Args:
        remote_name: The git remote name, e.g. ``upstream``.
        remote_url: The URL the remote should point at.

    Returns:
        ``True`` if the remote was newly created, ``False`` otherwise.

    Raises:
        SystemExit: If the remote exists but points to a different URL.
    """

    result = run_git_command("remote", capture_output=True)
    remotes = set(result.stdout.split())
    if remote_name not in remotes:
        run_git_command("remote", "add", remote_name, remote_url)
        return True

    existing_url = (
        run_git_command("remote", "get-url", remote_name, capture_output=True).stdout.strip()
    )
    if existing_url != remote_url:
        raise SystemExit(
            f"Remote '{remote_name}' already exists but points to '{existing_url}'.\n"
            f"Refusing to overwrite it with '{remote_url}'."
        )
    return False


def fetch_remote(remote_name: str, bundle_path: Optional[str] = None) -> None:
    """Fetch the latest refs from the configured upstream remote.

    When ``bundle_path`` is provided the refs are populated from the bundle
    instead of contacting the network. This makes it possible to work in
    restricted environments by shipping a ``git bundle`` alongside the repo.

    Args:
        remote_name: The remote to populate refs for (e.g. ``upstream``).
        bundle_path: Optional path to a local git bundle containing upstream
            history. When provided the bundle is fetched directly and the
            remote URL is not contacted.
    """

    if bundle_path:
        bundle = Path(bundle_path)
        if not bundle.is_file():
            raise SystemExit(
                f"Bundle path '{bundle}' does not exist or is not a file."
            )
        run_git_command(
            "fetch",
            "--force",
            "--tags",
            str(bundle),
            f"refs/heads/*:refs/remotes/{remote_name}/*",
        )
        return

    run_git_command("fetch", remote_name)


def resolve_current_branch() -> Optional[str]:
    """Return the current branch name, or ``None`` if HEAD is detached."""

    result = run_git_command("rev-parse", "--abbrev-ref", "HEAD", capture_output=True)
    branch_name = result.stdout.strip()
    if branch_name == "HEAD":
        return None
    return branch_name


def set_tracking_branch(remote_name: str, upstream_branch: str, local_branch: Optional[str]) -> None:
    """Configure the local branch to track the specified upstream branch."""

    remote_ref = f"{remote_name}/{upstream_branch}"
    try:
        run_git_command("show-ref", "--verify", f"refs/remotes/{remote_ref}", capture_output=True)
    except GitCommandError as exc:
        raise SystemExit(
            f"Remote branch '{remote_ref}' does not exist. Did you spell it correctly?"
        ) from exc

    if not local_branch:
        local_branch = resolve_current_branch()
        if local_branch is None:
            raise SystemExit(
                "Cannot set tracking branch while in a detached HEAD state. "
                "Provide --local-branch explicitly."
            )

    run_git_command(
        "branch",
        "--set-upstream-to",
        remote_ref,
        local_branch,
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Add and fetch the official Upload Assistant upstream remote, optionally "
            "configuring your current branch to track it."
        )
    )
    parser.add_argument(
        "--remote-name",
        default=DEFAULT_REMOTE_NAME,
        help=f"Name of the remote to configure (default: {DEFAULT_REMOTE_NAME!r}).",
    )
    parser.add_argument(
        "--remote-url",
        default=DEFAULT_REMOTE_URL,
        help="URL the remote should point to.",
    )
    parser.add_argument(
        "--bundle",
        metavar="PATH",
        help=(
            "Optional path to a git bundle that should be fetched instead of "
            "contacting the remote URL. Useful in offline environments."
        ),
    )
    parser.add_argument(
        "--track-branch",
        metavar="BRANCH",
        help=(
            "After fetching, configure the current branch (or --local-branch) to track "
            "the specified upstream branch."
        ),
    )
    parser.add_argument(
        "--local-branch",
        metavar="BRANCH",
        help=(
            "Local branch that should track the upstream branch. Defaults to the current "
            "branch if not provided and HEAD is attached."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    ensure_git_repository()

    created = ensure_remote(args.remote_name, args.remote_url)
    if created:
        print(f"Added remote '{args.remote_name}' -> {args.remote_url}")
    else:
        print(f"Remote '{args.remote_name}' already exists and matches the expected URL.")

    fetch_remote(args.remote_name, args.bundle)
    if args.bundle:
        print(
            f"Fetched updates for '{args.remote_name}' from bundle "
            f"'{args.bundle}'."
        )
    else:
        print(f"Fetched updates from '{args.remote_name}'.")

    if args.track_branch:
        set_tracking_branch(args.remote_name, args.track_branch, args.local_branch)
        target_branch = args.local_branch or resolve_current_branch()
        print(
            f"Local branch '{target_branch}' is now tracking "
            f"'{args.remote_name}/{args.track_branch}'."
        )

    return 0


if __name__ == "__main__":  # pragma: no cover - script entry point
    try:
        raise SystemExit(main())
    except GitCommandError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1)
