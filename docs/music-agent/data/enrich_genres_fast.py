"""
Fast genre enrichment using MusicBrainz + Wikipedia APIs.
Caches artist genres to avoid duplicate searches.

Usage:
    python enrich_genres_fast.py
"""

import json
import logging
import re
import sys
import time
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")
logger = logging.getLogger(__name__)

INPUT_PATH = Path("docs/music-agent/data/listening_history.json")
OUTPUT_PATH = Path("docs/music-agent/data/listening_history.json")
CACHE_PATH = Path("docs/music-agent/data/genre_cache.json")

HEADERS = {"User-Agent": "DeerFlow-MusicAgent/1.0 (deerflow@example.com)"}
MB_DELAY = 1.1

GENRE_CONTEXT_MAP = {
    "hip-hop": ["运动", "驾车"],
    "rap": ["运动", "驾车"],
    "trap": ["运动", "驾车"],
    "pop": ["工作", "社交"],
    "dance": ["运动", "派对"],
    "electronic": ["运动", "派对"],
    "house": ["运动", "派对"],
    "techno": ["运动", "派对"],
    "trance": ["运动", "深夜"],
    "edm": ["运动", "派对"],
    "dubstep": ["运动", "高能量"],
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
    "future bass": ["深夜", "独处"],
    "synthwave": ["深夜", "驾车"],
    "new wave": ["深夜", "独处"],
    "post-rock": ["深夜", "独处"],
    "singer-songwriter": ["深夜", "独处"],
    "acoustic": ["深夜", "独处"],
    "ballad": ["深夜", "独处"],
    "beat": ["工作", "专注"],
    "type beat": ["工作", "专注"],
}


def load_cache() -> dict[str, list[str]]:
    if CACHE_PATH.exists():
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache: dict[str, list[str]]):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def search_musicbrainz_artist_tags(artist: str) -> list[str]:
    try:
        url = f"https://musicbrainz.org/ws/2/artist/?query=artist:{requests.utils.quote(artist)}&fmt=json"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        artists = data.get("artists", [])
        if not artists:
            return []

        # Try tags from search result
        tags = artists[0].get("tags", [])
        if tags:
            return [t["name"] for t in tags[:5]]

        mbid = artists[0].get("id")
        if not mbid:
            return []

        time.sleep(MB_DELAY)
        url2 = f"https://musicbrainz.org/ws/2/artist/{mbid}?inc=tags&fmt=json"
        resp2 = requests.get(url2, headers=HEADERS, timeout=15)
        resp2.raise_for_status()
        data2 = resp2.json()
        tags = data2.get("tags", [])
        return [t["name"] for t in tags[:5]]
    except Exception as e:
        logger.debug(f"MusicBrainz fail: {artist} -> {e}")
        return []


def search_wikipedia_genre(artist: str) -> list[str]:
    try:
        url = (
            f"https://en.wikipedia.org/w/api.php?"
            f"action=query&list=search&srsearch={requests.utils.quote(artist + ' musician genre')}&"
            f"format=json&srlimit=1"
        )
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("query", {}).get("search", [])
        if not results:
            return []

        title = results[0].get("title", "")
        time.sleep(0.5)

        url2 = (
            f"https://en.wikipedia.org/w/api.php?"
            f"action=query&prop=extracts&exintro&titles={requests.utils.quote(title)}&"
            f"format=json&explaintext"
        )
        resp2 = requests.get(url2, headers=HEADERS, timeout=15)
        resp2.raise_for_status()
        data2 = resp2.json()
        pages = data2.get("query", {}).get("pages", {})
        for page in pages.values():
            extract = page.get("extract", "")
            matches = re.findall(
                r"(pop|rock|hip-hop|rap|electronic|dance|r&b|soul|jazz|blues|metal|alternative|indie|folk|country|classical|edm|trap|lo-fi|ambient|chill)(?:\s+(?:rock|pop|hop|music|artist|band))?",
                extract,
                re.IGNORECASE,
            )
            genres = []
            for m in matches:
                g = m[0] if isinstance(m, tuple) else m
                g = g.strip().lower()
                if g and len(g) > 2:
                    genres.append(g)
            return genres[:5]
        return []
    except Exception as e:
        logger.debug(f"Wikipedia fail: {artist} -> {e}")
        return []


def search_baidu_baike_genre(artist: str) -> list[str]:
    if not any("\u4e00" <= c <= "\u9fff" for c in artist):
        return []
    try:
        url = f"https://baike.baidu.com/item/{requests.utils.quote(artist)}"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        resp.raise_for_status()
        html = resp.text
        patterns = [
            r"流派[:\s]+([^<\n]+)",
            r"风格[:\s]+([^<\n]+)",
            r"类型[:\s]+([^<\n]+)",
            r"音乐类型[:\s]+([^<\n]+)",
        ]
        genres = []
        for pattern in patterns:
            for m in re.findall(pattern, html):
                g = re.sub(r"<[^>]+>", "", m).strip()
                if g:
                    genres.append(g)
        return genres[:5]
    except Exception as e:
        logger.debug(f"Baidu fail: {artist} -> {e}")
        return []


def dedup_genres(genres: list[str]) -> list[str]:
    seen = set()
    result = []
    for g in genres:
        gc = g.strip().lower()
        if gc in ("", "music", "artist", "band", "singer") or gc in seen:
            continue
        seen.add(gc)
        result.append(g.strip())
    return result[:3]


def infer_context_tags(genres: list[str]) -> list[str]:
    tags = set()
    for g in genres:
        gl = g.lower()
        for key, values in GENRE_CONTEXT_MAP.items():
            if key in gl:
                tags.update(values)
    return list(tags) if tags else []


def main():
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        songs = json.load(f)

    total = len(songs)
    logger.info(f"Loaded {total} songs")

    # Extract unique artists
    unique_artists = sorted({s["artist"].strip() for s in songs if s.get("artist")})
    logger.info(f"Unique artists: {len(unique_artists)}")

    # Load cache
    cache = load_cache()
    logger.info(f"Cache has {len(cache)} artists")

    # Find artists not in cache
    to_search = [a for a in unique_artists if a.lower() not in {k.lower() for k in cache}]
    logger.info(f"Need to search: {len(to_search)} artists")

    # Search each artist
    for idx, artist in enumerate(to_search, 1):
        logger.info(f"[{idx}/{len(to_search)}] Searching: {artist}")
        genres = []

        # 1. MusicBrainz
        mb = search_musicbrainz_artist_tags(artist)
        if mb:
            genres.extend(mb)
            logger.info(f"  MusicBrainz: {mb}")

        # 2. Wikipedia (if needed)
        if len(genres) < 2:
            time.sleep(0.5)
            wp = search_wikipedia_genre(artist)
            if wp:
                genres.extend(wp)
                logger.info(f"  Wikipedia: {wp}")

        # 3. Baidu (Chinese only)
        if len(genres) < 2:
            time.sleep(0.5)
            bd = search_baidu_baike_genre(artist)
            if bd:
                genres.extend(bd)
                logger.info(f"  Baidu: {bd}")

        genres = dedup_genres(genres)
        cache[artist] = genres

        if genres:
            logger.info(f"  => genre: {genres}")
        else:
            logger.info(f"  => genre: not found")

        # Save cache every 10 artists
        if idx % 10 == 0:
            save_cache(cache)
            logger.info(f"  Cache saved ({len(cache)} artists)")

        # Rate limit
        if idx < len(to_search):
            time.sleep(0.5)

    # Final save
    save_cache(cache)

    # Apply genres to all songs
    found = 0
    for song in songs:
        artist = song.get("artist", "").strip()
        # Find matching cache entry (case-insensitive)
        genres = []
        for k, v in cache.items():
            if k.lower() == artist.lower():
                genres = v
                break

        if genres:
            song["genre"] = ", ".join(genres)
            song["context_tags"] = infer_context_tags(genres)
            found += 1
        else:
            song["genre"] = ""
            song["context_tags"] = []

    # Write output
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(songs, f, ensure_ascii=False, indent=2)

    logger.info(f"\nDone! Enriched {found}/{total} songs ({found * 100 // total}%)")
    logger.info(f"Saved to: {OUTPUT_PATH}")
    logger.info(f"Cache: {CACHE_PATH}")

    # Show sample
    logger.info("\nSample results:")
    for s in songs[:10]:
        g = s.get("genre") or "(empty)"
        c = s.get("context_tags") or "(empty)"
        logger.info(f"  {s['track'][:40]:40s} | genre: {g}")


if __name__ == "__main__":
    main()
