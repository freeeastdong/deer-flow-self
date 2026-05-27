"""
Enrich listening history with genre and context_tags by searching music databases.

Usage:
    python enrich_genres.py listening_history.json output.json
"""

import json
import logging
import re
import sys
import time
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Rate limit: MusicBrainz requires 1 sec between requests
MB_DELAY = 1.1

# Genre to context_tags mapping
GENRE_CONTEXT_MAP = {
    "hip-hop": ["运动", "驾车"],
    "rap": ["运动", "驾车"],
    "pop": ["工作", "社交"],
    "dance": ["运动", "派对"],
    "electronic": ["运动", "派对"],
    "house": ["运动", "派对"],
    "techno": ["运动", "派对"],
    "trance": ["运动", "深夜"],
    "r&b": ["深夜", "独处"],
    "soul": ["深夜", "独处"],
    "rock": ["深夜", "独处"],
    "alternative": ["深夜", "独处"],
    "indie": ["深夜", "独处"],
    "metal": ["运动", "高能量"],
    "hardcore": ["运动", "高能量"],
    "punk": ["运动", "高能量"],
    "jazz": ["深夜", "放松"],
    "blues": ["深夜", "放松"],
    "classical": ["工作", "阅读"],
    "orchestral": ["工作", "阅读"],
    "bgm": ["工作", "专注"],
    "instrumental": ["工作", "专注"],
    "chill": ["深夜", "放松"],
    "lo-fi": ["工作", "深夜"],
    "ambient": ["工作", "深夜"],
    "folk": ["驾车", "午后"],
    "country": ["驾车", "午后"],
    "reggae": ["放松", "午后"],
    "latin": ["派对", "社交"],
    "k-pop": ["运动", "社交"],
    "j-pop": ["工作", "独处"],
    "mandopop": ["工作", "独处"],
    "c-pop": ["工作", "独处"],
    "soundtrack": ["工作", "深夜"],
    "ost": ["工作", "深夜"],
    "edm": ["运动", "派对"],
    "dubstep": ["运动", "高能量"],
    "drum and bass": ["运动", "高能量"],
    "trap": ["运动", "驾车"],
    "future bass": ["深夜", "独处"],
    "synthwave": ["深夜", "驾车"],
    "new wave": ["深夜", "独处"],
    "post-rock": ["深夜", "独处"],
    "shoegaze": ["深夜", "独处"],
    "dream pop": ["深夜", "独处"],
    "singer-songwriter": ["深夜", "独处"],
    "acoustic": ["深夜", "独处"],
    "ballad": ["深夜", "独处"],
    "beat": ["工作", "专注"],
    "type beat": ["工作", "专注"],
}


def search_musicbrainz_artist_tags(artist: str) -> list[str]:
    """Search MusicBrainz for artist tags (genres)."""
    try:
        # Search for artist
        url = f"https://musicbrainz.org/ws/2/artist/?query=artist:{requests.utils.quote(artist)}&fmt=json"
        headers = {"User-Agent": "DeerFlow-MusicAgent/1.0"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        artists = data.get("artists", [])
        if not artists:
            return []

        # Get top match
        mbid = artists[0].get("id")
        if not mbid:
            # Try to get tags from search result directly
            tags = artists[0].get("tags", [])
            return [t["name"] for t in tags[:5]]

        time.sleep(MB_DELAY)

        # Fetch artist with tags
        url2 = f"https://musicbrainz.org/ws/2/artist/{mbid}?inc=tags&fmt=json"
        resp2 = requests.get(url2, headers=headers, timeout=15)
        resp2.raise_for_status()
        data2 = resp2.json()

        tags = data2.get("tags", [])
        return [t["name"] for t in tags[:5]]

    except Exception as e:
        logger.debug(f"MusicBrainz failed for {artist}: {e}")
        return []


def search_wikipedia_genre(artist: str) -> list[str]:
    """Search Wikipedia for artist genre info."""
    try:
        url = (
            f"https://en.wikipedia.org/w/api.php?"
            f"action=query&list=search&srsearch={requests.utils.quote(artist + ' musician genre')}&"
            f"format=json&srlimit=1"
        )
        headers = {"User-Agent": "DeerFlow-MusicAgent/1.0"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        results = data.get("query", {}).get("search", [])
        if not results:
            return []

        title = results[0].get("title", "")

        time.sleep(0.5)

        # Get page extract
        url2 = (
            f"https://en.wikipedia.org/w/api.php?"
            f"action=query&prop=extracts&exintro&titles={requests.utils.quote(title)}&"
            f"format=json&explaintext"
        )
        resp2 = requests.get(url2, headers=headers, timeout=15)
        resp2.raise_for_status()
        data2 = resp2.json()

        pages = data2.get("query", {}).get("pages", {})
        for page in pages.values():
            extract = page.get("extract", "")
            # Look for genre mentions
            genre_patterns = [
                r"genres?[:\s]+([^\.\n]+)",
                r"(pop|rock|hip-hop|rap|electronic|dance|r&b|soul|jazz|blues|metal|alternative|indie|folk|country|classical|edm|trap|lo-fi|ambient|chill)(?:\s+(?:rock|pop|hop|music|artist|band))?",
            ]
            genres = []
            for pattern in genre_patterns:
                matches = re.findall(pattern, extract, re.IGNORECASE)
                for m in matches:
                    if isinstance(m, tuple):
                        m = m[0]
                    g = m.strip().lower()
                    if g and len(g) > 2:
                        genres.append(g)
            return genres[:5]

        return []

    except Exception as e:
        logger.debug(f"Wikipedia failed for {artist}: {e}")
        return []


def search_baidu_baike_genre(artist: str) -> list[str]:
    """Search Baidu Baike for Chinese artist genre info."""
    # Only search for Chinese artists
    if not any("\u4e00" <= c <= "\u9fff" for c in artist):
        return []

    try:
        url = f"https://baike.baidu.com/item/{requests.utils.quote(artist)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        html = resp.text

        # Look for genre info in Chinese
        patterns = [
            r"流派[:\s]+([^<\n]+)",
            r"风格[:\s]+([^<\n]+)",
            r"类型[:\s]+([^<\n]+)",
            r"音乐类型[:\s]+([^<\n]+)",
        ]
        genres = []
        for pattern in patterns:
            matches = re.findall(pattern, html)
            for m in matches:
                g = re.sub(r"<[^>]+>", "", m).strip()
                if g:
                    genres.append(g)
        return genres[:5]

    except Exception as e:
        logger.debug(f"Baidu Baike failed for {artist}: {e}")
        return []


def infer_context_tags(genres: list[str]) -> list[str]:
    """Infer context tags from genres."""
    tags = set()
    for genre in genres:
        g_lower = genre.lower()
        for key, values in GENRE_CONTEXT_MAP.items():
            if key in g_lower:
                tags.update(values)
    return list(tags) if tags else []


def deduplicate_genres(genres: list[str]) -> list[str]:
    """Deduplicate and clean genre list."""
    seen = set()
    result = []
    for g in genres:
        g_clean = g.strip().lower()
        # Skip non-meaningful tags
        if g_clean in ("", "music", "artist", "band", "singer"):
            continue
        if g_clean not in seen:
            seen.add(g_clean)
            result.append(g.strip())
    return result[:3]  # Keep top 3


def main():
    input_path = Path("docs/music-agent/data/listening_history.json")
    output_path = Path("docs/music-agent/data/listening_history.json")

    if len(sys.argv) >= 2:
        input_path = Path(sys.argv[1])
    if len(sys.argv) >= 3:
        output_path = Path(sys.argv[2])

    with open(input_path, "r", encoding="utf-8") as f:
        songs = json.load(f)

    total = len(songs)
    logger.info(f"Starting genre enrichment for {total} songs...")
    logger.info("Using MusicBrainz + Wikipedia + Baidu Baike...")
    logger.info("")

    # Cache artist genres to avoid duplicate searches
    artist_cache = {}

    for idx, song in enumerate(songs, 1):
        artist = song.get("artist", "").strip()
        track = song.get("track", "").strip()

        if not artist:
            continue

        # Use cache if available
        cache_key = artist.lower()
        if cache_key in artist_cache:
            genres = artist_cache[cache_key]
        else:
            genres = []

            # 1. Try MusicBrainz
            logger.info(f"[{idx}/{total}] Searching MusicBrainz: {artist}")
            mb_genres = search_musicbrainz_artist_tags(artist)
            if mb_genres:
                genres.extend(mb_genres)
                logger.info(f"  -> MusicBrainz: {mb_genres}")
            else:
                logger.info(f"  -> MusicBrainz: not found")

            # 2. Try Wikipedia (if MusicBrainz failed or gave few results)
            if len(genres) < 2:
                time.sleep(0.5)
                logger.info(f"  -> Searching Wikipedia...")
                wp_genres = search_wikipedia_genre(artist)
                if wp_genres:
                    genres.extend(wp_genres)
                    logger.info(f"  -> Wikipedia: {wp_genres}")

            # 3. Try Baidu Baike for Chinese artists
            if len(genres) < 2:
                time.sleep(0.5)
                logger.info(f"  -> Searching Baidu Baike...")
                bd_genres = search_baidu_baike_genre(artist)
                if bd_genres:
                    genres.extend(bd_genres)
                    logger.info(f"  -> Baidu: {bd_genres}")

            genres = deduplicate_genres(genres)
            artist_cache[cache_key] = genres

            # Rate limiting
            if idx < total:
                time.sleep(0.5)

        # Update song
        if genres:
            song["genre"] = ", ".join(genres)
            song["context_tags"] = infer_context_tags(genres)
            logger.info(f"  => genre: {song['genre']} | context: {song['context_tags']}")
        else:
            song["genre"] = ""
            song["context_tags"] = []
            logger.info(f"  => genre: (not found)")

        logger.info("")

    # Write output
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(songs, f, ensure_ascii=False, indent=2)

    # Stats
    found = sum(1 for s in songs if s.get("genre"))
    logger.info(f"\nDone! Found genres for {found}/{total} songs ({found*100//total}%)")
    logger.info(f"Saved to: {output_path}")


if __name__ == "__main__":
    main()
