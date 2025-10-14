import httpx
from pathlib import Path
from typing import Any, Optional

from data.config import config
from src.console import console


async def get_radarr_data(tmdb_id=None, filename=None, debug=False):
    if not any(key.startswith('radarr_api_key') for key in config['DEFAULT']):
        console.print("[red]No Radarr API keys are configured.[/red]")
        return None

    # Try each Radarr instance until we get valid data
    instance_index = 0
    max_instances = 4  # Limit instances to prevent infinite loops

    while instance_index < max_instances:
        # Determine the suffix for this instance
        suffix = "" if instance_index == 0 else f"_{instance_index}"
        api_key_name = f"radarr_api_key{suffix}"
        url_name = f"radarr_url{suffix}"

        # Check if this instance exists in config
        if api_key_name not in config['DEFAULT'] or not config['DEFAULT'][api_key_name]:
            # No more instances to try
            break

        # Get instance-specific configuration
        api_key = config['DEFAULT'][api_key_name].strip()
        base_url = config['DEFAULT'][url_name].strip()

        if debug:
            console.print(f"[blue]Trying Radarr instance {instance_index if instance_index > 0 else 'default'}[/blue]")

        # Build the appropriate URL
        if tmdb_id:
            url = f"{base_url}/api/v3/movie?tmdbId={tmdb_id}&excludeLocalCovers=true"
        elif filename:
            url = f"{base_url}/api/v3/movie/lookup?term={filename}"
        else:
            instance_index += 1
            continue

        headers = {
            "X-Api-Key": api_key,
            "Content-Type": "application/json"
        }

        if debug:
            console.print(f"[green]TMDB ID {tmdb_id}[/green]")
            console.print(f"[blue]Radarr URL:[/blue] {url}")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, timeout=10.0)

                if response.status_code == 200:
                    data = response.json()

                    if debug:
                        console.print(f"[blue]Radarr Response Status:[/blue] {response.status_code}")
                        console.print(f"[blue]Radarr Response Data:[/blue] {data}")

                    # Check if we got valid data by trying to extract movie info
                    movie_data = await extract_movie_data(data, filename)

                    if movie_data and (movie_data.get("imdb_id") or movie_data.get("tmdb_id")):
                        console.print(f"[green]Found valid movie data from Radarr instance {instance_index if instance_index > 0 else 'default'}[/green]")
                        return movie_data
                else:
                    console.print(f"[yellow]Failed to fetch from Radarr instance {instance_index if instance_index > 0 else 'default'}: {response.status_code} - {response.text}[/yellow]")

        except httpx.RequestError as e:
            console.print(f"[red]Error fetching from Radarr instance {instance_index if instance_index > 0 else 'default'}: {e}[/red]")
        except httpx.TimeoutException:
            console.print(f"[red]Timeout when fetching from Radarr instance {instance_index if instance_index > 0 else 'default'}[/red]")
        except Exception as e:
            console.print(f"[red]Unexpected error with Radarr instance {instance_index if instance_index > 0 else 'default'}: {e}[/red]")

        # Move to the next instance
        instance_index += 1

    # If we got here, no instances provided valid data
    console.print("[yellow]No Radarr instance returned valid movie data.[/yellow]")
    return None


def _normalize_tokens(value: Optional[str]) -> set[str]:
    """Return a set of comparable tokens for a filesystem path or name."""

    if not isinstance(value, str):
        return set()

    stripped = value.strip()
    if not stripped:
        return set()

    tokens = {stripped.lower()}

    try:
        path = Path(stripped)
    except Exception:
        return tokens

    parts = {path.name.lower()}
    if path.stem:
        parts.add(path.stem.lower())

    # Include parent directory names for folder comparisons (e.g. Radarr's
    # ``folder`` vs UA's ``uuid``).
    if path.parent != path:
        parts.add(path.parent.name.lower())

    tokens.update(part for part in parts if part)
    return tokens


def _match_movie_from_filename(radarr_data, filename: Optional[str]):
    if not filename:
        return None

    target_tokens = _normalize_tokens(filename)
    if not target_tokens:
        return None

    for item in radarr_data:
        movie_file = item.get("movieFile") or {}
        candidate_values = [
            movie_file.get("originalFilePath"),
            movie_file.get("path"),
            movie_file.get("relativePath"),
            item.get("path"),
            item.get("folder"),
            item.get("folderName"),
        ]

        candidate_tokens = set()
        for value in candidate_values:
            candidate_tokens.update(_normalize_tokens(value))

        if target_tokens & candidate_tokens:
            return item

    return None


async def extract_movie_data(radarr_data, filename=None):
    if not radarr_data or not isinstance(radarr_data, list) or len(radarr_data) == 0:
        return {
            "imdb_id": None,
            "tmdb_id": None,
            "year": None,
            "genres": [],
            "release_group": None,
            "movie": None,
        }

    movie = _match_movie_from_filename(radarr_data, filename) or radarr_data[0]

    release_group = None
    if movie.get("movieFile") and movie["movieFile"].get("releaseGroup"):
        release_group = movie["movieFile"]["releaseGroup"]

    return {
        "imdb_id": int(movie.get("imdbId", "tt0").replace("tt", "")) if movie.get("imdbId") else None,
        "tmdb_id": movie.get("tmdbId", None),
        "year": movie.get("year", None),
        "genres": movie.get("genres", []),
        "release_group": release_group if release_group else None,
        "movie": movie,
    }


def sceneNaming(movie_data: Optional[dict[str, Any]]) -> Optional[str]:
    """Return the raw scene name provided by Radarr for a movie file.

    Radarr exposes scene naming through ``movieFile.sceneName``.  The helper keeps
    Upload Assistant's behaviour aligned with Radarr by simply returning the
    trimmed value when available.
    """

    if not isinstance(movie_data, dict):
        return None

    movie_file = movie_data.get("movieFile") or {}
    scene_name = movie_file.get("sceneName")

    if not isinstance(scene_name, str):
        return None

    scene_name = scene_name.strip()
    return scene_name or None
