# -*- coding: utf-8 -*-
"""
扫描本地音乐文件（H:盘），读取元数据，导入 music_station.songs 表。
用法：python import_local_music.py
"""

import os
import sys
import io
import hashlib
import urllib.parse
from pathlib import Path

# Windows 控制台 UTF-8 编码修复
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import psycopg2
from mutagen import File as MutagenFile
from mutagen.mp4 import MP4
from mutagen.flac import FLAC

# ── 配置 ──────────────────────────────────────────────
DB_CONFIG = {
    "host": "localhost",
    "port": 5433,
    "dbname": "music_station",
    "user": "music",
    "password": "music123",
}

MUSIC_SOURCES = [
    {
        "name": "jay",
        "path": r"H:\JAY专辑AAC",
        "artist_default": "周杰伦",
        "genre_default": "Mandopop",
        "source": "local",
    },
    {
        "name": "taylor",
        "path": r"H:\Taylor Swift全集",
        "artist_default": "Taylor Swift",
        "genre_default": "Country Pop",
        "source": "local",
    },
]

VALID_EXTS = {".m4a", ".mp4", ".aac", ".flac", ".mp3", ".wav", ".ogg"}


def safe_get(meta, key, default=""):
    """安全获取 mutagen 元数据字段"""
    val = meta.get(key)
    if not val:
        return default
    # mutagen 返回的是列表，取第一个
    if isinstance(val, list):
        val = val[0]
    if isinstance(val, bytes):
        try:
            val = val.decode("utf-8")
        except UnicodeDecodeError:
            val = val.decode("gbk", errors="ignore")
    return str(val).strip() or default


def parse_m4a_metadata(filepath: str) -> dict:
    """读取 AAC/M4A 文件元数据"""
    try:
        audio = MP4(filepath)
    except Exception as e:
        print(f"  [警告] 无法解析 {filepath}: {e}")
        return {}

    tags = audio.tags or {}
    # MP4 标签键是 \xa9nam, \xa9ART, \xa9alb, \xa9gen
    title = safe_get(tags, "\xa9nam")
    artist = safe_get(tags, "\xa9ART")
    album = safe_get(tags, "\xa9alb")
    genre = safe_get(tags, "\xa9gen")
    duration = int(audio.info.length) if audio.info else 0

    return {
        "title": title,
        "artist": artist,
        "album": album,
        "genre": genre,
        "duration": duration,
    }


def parse_flac_metadata(filepath: str) -> dict:
    """读取 FLAC 文件元数据"""
    try:
        audio = FLAC(filepath)
    except Exception as e:
        print(f"  [警告] 无法解析 {filepath}: {e}")
        return {}

    tags = audio.tags or {}
    title = safe_get(tags, "TITLE")
    artist = safe_get(tags, "ARTIST")
    album = safe_get(tags, "ALBUM")
    genre = safe_get(tags, "GENRE")
    duration = int(audio.info.length) if audio.info else 0

    return {
        "title": title,
        "artist": artist,
        "album": album,
        "genre": genre,
        "duration": duration,
    }


def parse_generic_metadata(filepath: str) -> dict:
    """通用音频文件解析"""
    try:
        audio = MutagenFile(filepath)
    except Exception as e:
        print(f"  [警告] 无法解析 {filepath}: {e}")
        return {}

    if audio is None:
        return {}

    tags = getattr(audio, "tags", {}) or {}
    # 尝试多种常见键名
    title = safe_get(tags, "TIT2") or safe_get(tags, "TITLE") or safe_get(tags, "\xa9nam")
    artist = safe_get(tags, "TPE1") or safe_get(tags, "ARTIST") or safe_get(tags, "\xa9ART")
    album = safe_get(tags, "TALB") or safe_get(tags, "ALBUM") or safe_get(tags, "\xa9alb")
    genre = safe_get(tags, "TCON") or safe_get(tags, "GENRE") or safe_get(tags, "\xa9gen")
    duration = int(audio.info.length) if hasattr(audio, "info") and audio.info else 0

    return {
        "title": title,
        "artist": artist,
        "album": album,
        "genre": genre,
        "duration": duration,
    }


def read_metadata(filepath: str) -> dict:
    """根据扩展名选择解析器"""
    ext = Path(filepath).suffix.lower()
    if ext == ".m4a" or ext == ".mp4":
        meta = parse_m4a_metadata(filepath)
    elif ext == ".flac":
        meta = parse_flac_metadata(filepath)
    else:
        meta = parse_generic_metadata(filepath)

    return meta


def generate_audio_url(source_name: str, rel_path: str) -> str:
    """生成 nginx 可访问的 audio_url"""
    # rel_path 是相对于源目录的路径，例如 "2001 Jay Fantasy - EP/01 可爱女人.m4a"
    # URL 需要编码
    parts = rel_path.replace("\\", "/").split("/")
    encoded_parts = [urllib.parse.quote(part, safe="") for part in parts]
    url_path = "/".join(encoded_parts)
    return f"/api/music-station/media/local/{source_name}/{url_path}"


def file_hash(filepath: str) -> str:
    """取文件前 64KB 的 md5 作为去重标识"""
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        h.update(f.read(65536))
    return h.hexdigest()


def scan_source(source_cfg: dict) -> list:
    """扫描一个源目录，返回歌曲记录列表"""
    root = Path(source_cfg["path"])
    records = []
    if not root.exists():
        print(f"[跳过] 目录不存在: {root}")
        return records

    files = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in VALID_EXTS]
    print(f"[扫描] {source_cfg['name']} -> {len(files)} 个音频文件")

    for idx, filepath in enumerate(files, 1):
        rel = str(filepath.relative_to(root))
        print(f"  [{idx}/{len(files)}] {rel}", end="")

        meta = read_metadata(str(filepath))
        if not meta:
            print(" -> 解析失败，跳过")
            continue

        # 如果没有从文件读出 title，用文件名（去掉序号前缀和扩展名）
        title = meta.get("title", "")
        if not title:
            # 去掉类似 "01 ", "1-01 ", "CD1/01 " 这样的前缀
            stem = filepath.stem
            # 尝试去掉数字前缀
            import re
            stem = re.sub(r"^\d+[-_]?\d*\s*[-_.]?\s*", "", stem).strip()
            title = stem or filepath.name

        artist = meta.get("artist", "") or source_cfg["artist_default"]
        album = meta.get("album", "")
        genre = meta.get("genre", "") or source_cfg["genre_default"]
        duration = meta.get("duration", 0)

        audio_url = generate_audio_url(source_cfg["name"], rel)
        source_id = file_hash(str(filepath))

        records.append({
            "title": title,
            "artist": artist,
            "album": album,
            "genre": genre,
            "audio_url": audio_url,
            "cover_url": None,
            "duration": duration,
            "tags": "",
            "mood": None,
            "scene": None,
            "instrument": None,
            "source": source_cfg["source"],
            "source_id": source_id,
        })
        print(f" -> {title} / {artist}")

    return records


def insert_into_db(records: list):
    """批量插入数据库"""
    if not records:
        print("[信息] 没有记录需要导入")
        return

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # 先查询已有的 source_id，去重
    cur.execute("SELECT source_id FROM songs WHERE source = 'local'")
    existing = {row[0] for row in cur.fetchall()}
    print(f"[信息] 数据库中已有 {len(existing)} 条本地音乐记录")

    new_records = [r for r in records if r["source_id"] not in existing]
    duplicates = len(records) - len(new_records)
    if duplicates:
        print(f"[信息] 跳过 {duplicates} 条重复记录")

    if not new_records:
        print("[信息] 没有新记录需要导入")
        cur.close()
        conn.close()
        return

    sql = """
    INSERT INTO songs (
        title, artist, album, genre, audio_url, cover_url, duration,
        tags, mood, scene, instrument, source, source_id
    ) VALUES (
        %(title)s, %(artist)s, %(album)s, %(genre)s, %(audio_url)s, %(cover_url)s, %(duration)s,
        %(tags)s, %(mood)s, %(scene)s, %(instrument)s, %(source)s, %(source_id)s
    )
    """

    batch_size = 50
    total = len(new_records)
    for i in range(0, total, batch_size):
        batch = new_records[i : i + batch_size]
        cur.executemany(sql, batch)
        conn.commit()
        print(f"[插入] {min(i + batch_size, total)}/{total} ...")

    cur.close()
    conn.close()
    print(f"[完成] 成功导入 {total} 条记录")


def main():
    all_records = []
    for src in MUSIC_SOURCES:
        records = scan_source(src)
        all_records.extend(records)

    print(f"\n[总计] 扫描到 {len(all_records)} 首歌曲")
    insert_into_db(all_records)


if __name__ == "__main__":
    main()
