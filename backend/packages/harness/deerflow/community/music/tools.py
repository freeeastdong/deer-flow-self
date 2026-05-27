"""
Music Tools - Last.fm API integration for music search, similar tracks, and artist info.

Requires LASTFM_API_KEY environment variable or api_key in config.yaml tool config.
Get a free API key at: https://www.last.fm/api/account/create
"""

import json
import logging
import os
from typing import Any

import requests
from langchain.tools import tool

from deerflow.config import get_app_config

logger = logging.getLogger(__name__)

LASTFM_API_BASE = "https://ws.audioscrobbler.com/2.0/"


def _get_lastfm_api_key(tool_name: str = "music_search") -> str | None:
    """Get Last.fm API key from config or environment."""
    config = get_app_config().get_tool_config(tool_name)
    if config is not None and "api_key" in config.model_extra:
        return config.model_extra.get("api_key")
    return os.environ.get("LASTFM_API_KEY")


def _lastfm_request(method: str, params: dict[str, Any]) -> dict[str, Any]:
    """Make a Last.fm API request."""
    api_key = _get_lastfm_api_key()
    if not api_key:
        raise RuntimeError(
            "Last.fm API key not found. Set LASTFM_API_KEY environment variable "
            "or configure api_key in config.yaml tools section."
        )

    request_params = {
        "method": method,
        "api_key": api_key,
        "format": "json",
        **params,
    }

    try:
        response = requests.get(LASTFM_API_BASE, params=request_params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            error_msg = data.get("message", "Unknown Last.fm API error")
            raise RuntimeError(f"Last.fm API error: {error_msg}")

        return data
    except requests.RequestException as e:
        logger.error(f"Last.fm API request failed: {e}")
        raise RuntimeError(f"Failed to connect to Last.fm API: {e}")


@tool("music_search", parse_docstring=True)
def music_search_tool(query: str, limit: int = 5) -> str:
    """Search for songs, artists, or albums using Last.fm API.

    Args:
        query: Search keywords (song name, artist name, or album name).
        limit: Maximum number of results to return (default: 5).
    """
    try:
        data = _lastfm_request("track.search", {"track": query, "limit": limit})
        tracks = data.get("results", {}).get("trackmatches", {}).get("track", [])

        if not tracks:
            return json.dumps(
                {"results": [], "message": "No tracks found for the given query."},
                ensure_ascii=False,
                indent=2,
            )

        # Ensure tracks is a list (Last.fm returns a dict for single result)
        if isinstance(tracks, dict):
            tracks = [tracks]

        results = []
        for track in tracks[:limit]:
            results.append(
                {
                    "track": track.get("name", ""),
                    "artist": track.get("artist", ""),
                    "listeners": track.get("listeners", "0"),
                    "url": track.get("url", ""),
                }
            )

        return json.dumps({"results": results, "query": query}, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False, indent=2)


@tool("music_similar_tracks", parse_docstring=True)
def music_similar_tracks_tool(artist: str, track: str, limit: int = 5) -> str:
    """Get similar tracks based on a given song using Last.fm API.

    Args:
        artist: Artist name.
        track: Track name.
        limit: Maximum number of similar tracks to return (default: 5).
    """
    try:
        data = _lastfm_request(
            "track.getSimilar",
            {"artist": artist, "track": track, "limit": limit},
        )
        tracks = data.get("similartracks", {}).get("track", [])

        if not tracks:
            return json.dumps(
                {"results": [], "message": f"No similar tracks found for '{track}' by '{artist}'."},
                ensure_ascii=False,
                indent=2,
            )

        if isinstance(tracks, dict):
            tracks = [tracks]

        results = []
        for t in tracks[:limit]:
            results.append(
                {
                    "track": t.get("name", ""),
                    "artist": t.get("artist", {}).get("name", ""),
                    "match": t.get("match", "0"),
                    "url": t.get("url", ""),
                }
            )

        return json.dumps(
            {"results": results, "source": {"artist": artist, "track": track}},
            ensure_ascii=False,
            indent=2,
        )

    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False, indent=2)


@tool("music_artist_info", parse_docstring=True)
def music_artist_info_tool(artist: str, limit: int = 5) -> str:
    """Get artist information including top tracks, tags, and similar artists using Last.fm API.

    Args:
        artist: Artist name.
        limit: Maximum number of top tracks and similar artists to return (default: 5).
    """
    try:
        # Get artist info
        info_data = _lastfm_request("artist.getInfo", {"artist": artist})
        artist_info = info_data.get("artist", {})

        if not artist_info:
            return json.dumps(
                {"error": f"Artist '{artist}' not found."},
                ensure_ascii=False,
                indent=2,
            )

        # Get top tracks
        top_tracks_data = _lastfm_request(
            "artist.getTopTracks", {"artist": artist, "limit": limit}
        )
        top_tracks = top_tracks_data.get("toptracks", {}).get("track", [])
        if isinstance(top_tracks, dict):
            top_tracks = [top_tracks]

        tracks_list = []
        for t in top_tracks[:limit]:
            tracks_list.append(
                {
                    "track": t.get("name", ""),
                    "playcount": t.get("playcount", "0"),
                    "listeners": t.get("listeners", "0"),
                    "url": t.get("url", ""),
                }
            )

        # Get similar artists
        similar_artists = artist_info.get("similar", {}).get("artist", [])
        if isinstance(similar_artists, dict):
            similar_artists = [similar_artists]

        similar_list = []
        for a in similar_artists[:limit]:
            similar_list.append(
                {
                    "artist": a.get("name", ""),
                    "url": a.get("url", ""),
                }
            )

        # Get tags (genres)
        tags = artist_info.get("tags", {}).get("tag", [])
        if isinstance(tags, dict):
            tags = [tags]
        tags_list = [t.get("name", "") for t in tags]

        result = {
            "artist": artist_info.get("name", artist),
            "bio": artist_info.get("bio", {}).get("summary", ""),
            "listeners": artist_info.get("stats", {}).get("listeners", "0"),
            "playcount": artist_info.get("stats", {}).get("playcount", "0"),
            "tags": tags_list,
            "top_tracks": tracks_list,
            "similar_artists": similar_list,
            "url": artist_info.get("url", ""),
        }

        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False, indent=2)
