"""Tests for client linking helpers."""
from __future__ import annotations

import asyncio
import os

from src.clients import Clients


def _make_clients() -> Clients:
    return Clients({})


def test_build_dest_path_prefers_radarr_scene_name(tmp_path):
    clients = _make_clients()
    tracker_dir = tmp_path / "TRACKER"
    tracker_dir.mkdir()

    src_path = tmp_path / "source" / "Original.Movie.2160p.mkv"
    src_path.parent.mkdir()
    src_path.write_text("dummy")

    meta = {
        "preferred_scene_name": "Movie.Scene.Name.2160p.UHD",  # extension added by helper
        "name": "Original.Movie.2160p.mkv",
        "filelist": [str(src_path)],
    }

    dest_path, rename_target = clients._build_dest_path(str(src_path), str(tracker_dir), meta)

    expected = tracker_dir / "Movie.Scene.Name.2160p.UHD.mkv"
    assert dest_path == os.fspath(expected)
    assert rename_target == "Movie.Scene.Name.2160p.UHD.mkv"


def test_build_dest_path_directory_uses_preferred_scene_name(tmp_path):
    clients = _make_clients()
    tracker_dir = tmp_path / "TRACKER"
    tracker_dir.mkdir()

    src_dir = tmp_path / "Original.Movie.2160p"
    (src_dir / "BDMV").mkdir(parents=True)

    meta = {
        "preferred_scene_name": "Movie.Scene.Name.2160p.UHD.BluRay.Remux",
        "name": "Original.Movie.2160p",
    }

    dest_path, rename_target = clients._build_dest_path(str(src_dir), str(tracker_dir), meta)

    expected = tracker_dir / "Movie.Scene.Name.2160p.UHD.BluRay.Remux"
    assert dest_path == os.fspath(expected)
    assert rename_target == "Movie.Scene.Name.2160p.UHD.BluRay.Remux"


def test_qbittorrent_links_with_scene_name(tmp_path, monkeypatch):
    async def run_test():
        linked_root = tmp_path / "linked"
        linked_root.mkdir()

        config = {
            "DEFAULT": {"default_torrent_client": "qbit"},
            "TORRENT_CLIENTS": {
                "qbit": {
                    "torrent_client": "qbit",
                    "linking": "hardlink",
                    "linked_folder": [os.fspath(linked_root)],
                    "qbit_url": "http://localhost",
                    "qbit_port": 8080,
                    "qbit_user": "user",
                    "qbit_pass": "pass",
                    "content_layout": "Original",
                }
            },
            "TRACKERS": {
                "allow_fallback": False,
                "MTV": {"link_dir_name": ""},
            },
        }

        clients = Clients(config)

        src_dir = tmp_path / "source"
        src_dir.mkdir()
        src_file = src_dir / "Original.Movie.2160p.mkv"
        src_file.write_text("dummy")

        meta = {
            "keep_folder": False,
            "filelist": [os.fspath(src_file)],
            "path": os.fspath(src_file),
            "debug": False,
            "linking_info": {},
            "preferred_scene_name": "Movie.Scene.Name.2160p.UHD",
            "name": "Original.Movie.2160p.mkv",
        }

        class DummyTorrent:
            infohash = "ABCDEF1234567890"
            name = "Original.Movie.2160p.mkv"

            @staticmethod
            def dump():
                return b"torrent"

        class DummyClient:
            def __init__(self, **_):
                self.add_kwargs = None

            def auth_log_in(self):
                return None

            def torrents_add(self, **kwargs):
                self.add_kwargs = kwargs

            def torrents_info(self, **_):
                return [object()]

            def torrents_resume(self, *_):
                return None

            def torrents_add_tags(self, **_):
                return None

        dummy_holder = {}

        def make_dummy_client(**kwargs):
            dummy_holder["client"] = DummyClient(**kwargs)
            return dummy_holder["client"]

        import src.clients as clients_mod

        monkeypatch.setattr(clients_mod.qbittorrentapi, "Client", make_dummy_client)

        async def fake_link(src, dst, use_hardlink=True, debug=False):
            dummy_holder["link_args"] = (src, dst, use_hardlink, debug)
            return True

        monkeypatch.setattr(clients_mod, "async_link_directory", fake_link)

        async def fake_retry(self, operation_func, *_args, **_kwargs):
            return await operation_func()

        monkeypatch.setattr(Clients, "retry_qbt_operation", fake_retry, raising=False)

        await clients.qbittorrent(
            path=meta["path"],
            torrent=DummyTorrent(),
            local_path=None,
            remote_path=None,
            client=config["TORRENT_CLIENTS"]["qbit"],
            is_disc=False,
            filelist=meta["filelist"],
            meta=meta,
            tracker="MTV",
        )

        dest_path = os.path.join(
            os.fspath(linked_root / "MTV"), "Movie.Scene.Name.2160p.UHD.mkv"
        )

        assert dummy_holder["link_args"][1] == dest_path
        dummy_client = dummy_holder["client"]
        assert dummy_client.add_kwargs["rename"] == "Movie.Scene.Name.2160p.UHD.mkv"

    asyncio.run(run_test())
