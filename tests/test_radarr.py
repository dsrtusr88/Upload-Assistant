import asyncio
import sys
import types

stub_config = types.ModuleType("data.config")
stub_config.config = {"DEFAULT": {}}
sys.modules.setdefault("data", types.ModuleType("data"))
sys.modules["data.config"] = stub_config

from src.radarr import extract_movie_data


def test_extract_movie_data_matches_folder_name():
    radarr_payload = [
        {
            "tmdbId": 1100800,
            "imdbId": "tt38346012",
            "year": 2025,
            "genres": ["Drama", "Romance"],
            "folder": "The Balloonist (2025)",
            "folderName": "/media/Movies/The Balloonist (2025)",
            "movieFile": {
                "originalFilePath": "De.Ballonvaarder.2025.2160p.DSNP.WEB-DL.DDP5.1.HDR.HEVC-playWEB/De.Ballonvaarder.2025.2160p.DSNP.WEB-DL.DD5.1.HDR.H.265-playWEB.mkv",
                "sceneName": "De.Ballonvaarder.2025.2160p.DSNP.WEB-DL.DDP5.1.HDR.HEVC-playWEB",
            },
        },
        {
            "tmdbId": 1382575,
            "imdbId": "tt29719486",
            "year": 2025,
            "genres": ["Documentary"],
            "folder": "The Balloonists (2025)",
        },
    ]

    result = asyncio.run(extract_movie_data(radarr_payload, filename="The Balloonist (2025)"))

    assert result["tmdb_id"] == 1100800
    assert result["imdb_id"] == 38346012
    assert result["year"] == 2025
    assert result["genres"] == ["Drama", "Romance"]
    assert result["movie"]["movieFile"]["sceneName"].startswith("De.Ballonvaarder")


def test_extract_movie_data_falls_back_to_first_entry():
    radarr_payload = [
        {
            "tmdbId": 1100800,
            "imdbId": "tt38346012",
            "year": 2025,
            "genres": ["Drama", "Romance"],
            "movieFile": {"sceneName": "De.Ballonvaarder.2025"},
        },
        {
            "tmdbId": 1382575,
            "imdbId": "tt29719486",
            "year": 2025,
            "genres": ["Documentary"],
        },
    ]

    result = asyncio.run(extract_movie_data(radarr_payload, filename="not-a-match"))

    assert result["tmdb_id"] == 1100800
    assert result["imdb_id"] == 38346012
    assert result["genres"] == ["Drama", "Romance"]
