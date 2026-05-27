"""
Parse NetEase Cloud Music playlist HTML to extract song list.

Usage:
    python parse_netease_html.py input.html output.json
"""

import json
import re
import sys
from pathlib import Path


def parse_netease_playlist_html(html_path: str) -> list[dict]:
    """Parse NetEase playlist HTML and extract song information."""
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    songs = []

    # Find all song items: <a class="m-sgitem" href="//music.163.com/m/song?id=NUMBER">
    # Each item contains:
    #   <div class="f-thide sgtl">SONG_NAME</div>
    #   <div class="f-thide sginfo">ARTIST - ALBUM</div>

    # Pattern to match one complete song block
    pattern = re.compile(
        r'<a class="m-sgitem"[^>]*href="//music\.163\.com/m/song\?id=(\d+)[^"]*"[^>]*>.*?'
        r'<div class="f-thide sgtl">(.*?)</div>.*?'
        r'<div class="f-thide sginfo">(.*?)<!--\s*-->'
        r'\s*-\s*(.*?)</div>',
        re.DOTALL,
    )

    matches = pattern.findall(html)

    for idx, match in enumerate(matches, 1):
        song_id, title_raw, artist_raw, album_raw = match

        # Clean up HTML entities and whitespace
        title = _clean_text(title_raw)
        artist = _clean_text(artist_raw)
        album = _clean_text(album_raw)

        # Skip if essential data is missing
        if not title or not artist:
            continue

        song = {
            "track_id": f"netease_{song_id}",
            "track": title,
            "artist": artist,
            "album": album if album else "",
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


def _clean_text(text: str) -> str:
    """Clean HTML entities and extra whitespace."""
    # Decode common HTML entities
    text = text.replace("&quot;", '"')
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&nbsp;", " ")
    text = text.replace("&#39;", "'")

    # Remove remaining HTML tags
    text = re.sub(r"<[^>]+>", "", text)

    # Normalize whitespace
    text = " ".join(text.split())

    return text.strip()


def main():
    input_path = Path("docs/music-agent/data/text.txt")
    output_path = Path("docs/music-agent/data/listening_history.json")

    if len(sys.argv) >= 2:
        input_path = Path(sys.argv[1])
    if len(sys.argv) >= 3:
        output_path = Path(sys.argv[2])

    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)

    songs = parse_netease_playlist_html(str(input_path))

    if not songs:
        print("Warning: No songs found in the HTML file.")
        sys.exit(1)

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(songs, f, ensure_ascii=False, indent=2)

    print(f"Successfully extracted {len(songs)} songs from {input_path}")
    print(f"Saved to: {output_path}")

    # Print summary
    print("\nTop 10 songs:")
    for song in songs[:10]:
        print(f"  {song['rank']}. {song['track']} - {song['artist']}")
        if song['album']:
            print(f"     Album: {song['album']}")


if __name__ == "__main__":
    main()
