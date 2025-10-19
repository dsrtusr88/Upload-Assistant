"""Tests for the ``bin/setup_upstream.py`` helper script."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import bin.setup_upstream as setup_upstream


def run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Execute a git command inside ``cwd`` and return the process."""

    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def create_upstream_bundle(tmp_path: Path) -> tuple[Path, str]:
    """Create a small git repository and return a bundle path and commit."""

    upstream = tmp_path / "upstream"
    upstream.mkdir()
    run_git(["init", "--initial-branch=master"], upstream)
    run_git(["config", "user.email", "ci@example.com"], upstream)
    run_git(["config", "user.name", "CI"], upstream)

    (upstream / "README.md").write_text("hello upstream\n", encoding="utf-8")
    run_git(["add", "README.md"], upstream)
    run_git(["commit", "-m", "initial"], upstream)

    commit = (
        run_git(["rev-parse", "HEAD"], upstream).stdout.strip()
    )

    bundle_path = tmp_path / "upstream.bundle"
    run_git(["bundle", "create", str(bundle_path), "master"], upstream)
    return bundle_path, commit


def test_fetch_remote_from_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``fetch_remote`` should populate remote refs from a provided bundle."""

    bundle_path, commit = create_upstream_bundle(tmp_path)

    target = tmp_path / "target"
    target.mkdir()
    run_git(["init"], target)

    monkeypatch.chdir(target)
    setup_upstream.ensure_remote("upstream", "https://example.invalid/Upload-Assistant.git")
    setup_upstream.fetch_remote("upstream", str(bundle_path))

    rev = (
        run_git(["rev-parse", "refs/remotes/upstream/master"], target)
        .stdout.strip()
    )
    assert rev == commit


def test_fetch_remote_missing_bundle(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Providing a non-existent bundle should raise ``SystemExit``."""

    target = tmp_path / "target"
    target.mkdir()
    run_git(["init"], target)

    monkeypatch.chdir(target)
    setup_upstream.ensure_remote("upstream", "https://example.invalid/Upload-Assistant.git")

    missing = tmp_path / "does-not-exist.bundle"
    with pytest.raises(SystemExit):
        setup_upstream.fetch_remote("upstream", str(missing))
