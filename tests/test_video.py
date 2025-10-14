"""Tests for interactive helpers in ``src.video``."""

from __future__ import annotations

import asyncio
import os

from src import video


class _ResponseQueue:
    """Simple helper to provide deterministic CLI responses."""

    def __init__(self, *responses: str | None) -> None:
        self._responses = list(responses)

    def pop(self) -> str | None:
        if not self._responses:
            raise AssertionError("No more responses available for CLI prompt")
        return self._responses.pop(0)


def test_prompt_filename_correction_renames_file(tmp_path, monkeypatch):
    original = tmp_path / "Example.Movie (2024) {tmdb-1}.mkv"
    original.write_text("test")

    queue = _ResponseQueue("Example.Movie.2024.WEB-DL")
    monkeypatch.setattr(video.cli_ui, "ask_string", lambda *_, **__: queue.pop())

    new_path = asyncio.run(video.prompt_filename_correction(str(original)))

    expected_path = tmp_path / "Example.Movie.2024.WEB-DL.mkv"
    assert new_path == os.path.abspath(expected_path)
    assert expected_path.exists()
    assert not original.exists()


def test_prompt_filename_correction_skip(tmp_path, monkeypatch):
    original = tmp_path / "Example.Movie (2024) {tmdb-1}.mkv"
    original.write_text("test")

    queue = _ResponseQueue("")
    monkeypatch.setattr(video.cli_ui, "ask_string", lambda *_, **__: queue.pop())

    new_path = asyncio.run(video.prompt_filename_correction(str(original)))

    assert new_path is None
    assert original.exists()
