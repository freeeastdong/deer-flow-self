"""
Parse NetEase Cloud Music playlist JSON API response.

Usage:
    python parse_netease_json.py input.json output.json
"""

import json
import sys
from pathlib import Path


def parse_netease_playlist_json(json_path: str) -> list[dict]:
    """Parse NetEase playlist JSON and extract all songs."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    playlist = data.get("playlist", {})
    tracks = playlist.get("tracks", [])

    songs = []
    for idx, track in enumerate(tracks, 1):
        song_id = track.get("id", "")
        title = track.get("name", "").strip()

        # Artist(s)
        artists = track.get("ar", [])
        if artists:
            artist_names = [a.get("name", "").strip() for a in artists if a.get("name")]
            artist = " / ".join(artist_names) if len(artist_names) > 1 else artist_names[0]
        else:
            artist = ""

        # Album
        album_info = track.get("al", {})
        album = album_info.get("name", "").strip() if album_info else ""

        # Duration (ms -> mm:ss for reference)
        duration_ms = track.get("dt", 0)

        # Popularity (0-100)
        pop = track.get("pop", 0)

        # Skip if no title or artist
        if not title:
            continue

        song = {
            "track_id": f"netease_{song_id}",
            "track": title,
            "artist": artist,
            "album": album,
            "genre": "",
            "play_count": 0,
            "is_liked": True,
            "rank": idx,
            "source": "netease",
            "timestamp_range": "",
            "context_tags": [],
        }
        songs.append(song)

    return songs


def main():
    input_path = Path("docs/music-agent/data/text02.txt")
    output_path = Path("docs/music-agent/data/listening_history.json")

    if len(sys.argv) >= 2:
        input_path = Path(sys.argv[1])
    if len(sys.argv) >= 3:
        output_path = Path(sys.argv[2])

    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)

    songs = parse_netease_playlist_json(str(input_path))

    if not songs:
        print("Warning: No songs found in the JSON file.")
        sys.exit(1)

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(songs, f, ensure_ascii=False, indent=2)

    print(f"Successfully extracted {len(songs)} songs from {input_path}")
    print(f"Saved to: {output_path}")

    # Print summary
    print(f"\nTop 20 songs:")
    for song in songs[:20]:
        album_str = f" [{song['album']}]" if song["album"] else ""
        print(f"  {song['rank']:3d}. {song['track']} - {song['artist']}{album_str}")

    if len(songs) > 20:
        print(f"  ... and {len(songs) - 20} more")


if __name__ == "__main__":
    main()
