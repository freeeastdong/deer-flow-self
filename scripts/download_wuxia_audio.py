#!/usr/bin/env python3
"""搜索并下载B站武侠/邵氏风格音频素材"""
import json
import urllib.request
import urllib.parse
import subprocess
import os
import sys

TARGET_DIR = r"H:\视频素材\邵氏武侠音色"
os.makedirs(TARGET_DIR, exist_ok=True)

def search_bilibili(keyword, max_results=5):
    """通过B站搜索API查找视频"""
    encoded = urllib.parse.quote(keyword)
    # 使用web搜索API
    url = f"https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword={encoded}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://search.bilibili.com/"
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("data", {}).get("result", []):
                results = []
                for v in data["data"]["result"][:max_results]:
                    results.append({
                        "bvid": v.get("bvid", ""),
                        "title": v.get("title", "").replace("<em class=\"keyword\">", "").replace("</em>", ""),
                        "link": v.get("arcurl", "")
                    })
                return results
    except Exception as e:
        print(f"Search error for '{keyword}': {e}")
    return []

def download_audio(bvid, title, target_dir):
    """用yt-dlp下载B站视频的最佳音频"""
    url = f"https://www.bilibili.com/video/{bvid}"
    safe_title = "".join(c for c in title if c.isalnum() or c in " _-").strip()[:50]
    output_template = os.path.join(target_dir, f"{safe_title}_%(id)s.%(ext)s")
    
    cmd = [
        "yt-dlp",
        "-f", "ba",           # best audio only
        "--no-video",
        "--no-playlist",
        "-o", output_template,
        url
    ]
    print(f"\n[下载] {title} ({bvid})")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            print(f"[成功] {title}")
            return True
        else:
            print(f"[失败] {title}\n{result.stderr[:300]}")
            return False
    except Exception as e:
        print(f"[错误] {e}")
        return False

def main():
    # 搜索关键词列表
    queries = [
        "邵氏电影经典对白",
        "港片霸气台词国语配音",
        "武侠电影经典台词",
        "老港片国语配音",
        "金庸武侠经典对白",
    ]
    
    all_videos = []
    for q in queries:
        print(f"\n搜索: {q}")
        videos = search_bilibili(q, max_results=3)
        for v in videos:
            if v["bvid"] and v["bvid"] not in [x["bvid"] for x in all_videos]:
                all_videos.append(v)
                print(f"  + {v['bvid']} | {v['title'][:60]}")
    
    print(f"\n共找到 {len(all_videos)} 个视频，开始下载音频...")
    
    success_count = 0
    for v in all_videos[:8]:  # 最多下载8个
        if download_audio(v["bvid"], v["title"], TARGET_DIR):
            success_count += 1
    
    print(f"\n下载完成: {success_count}/{len(all_videos[:8])} 个成功")
    print(f"保存位置: {TARGET_DIR}")
    
    # 列出已下载的文件
    files = os.listdir(TARGET_DIR)
    print(f"\n目录中已有 {len(files)} 个文件:")
    for f in files:
        fpath = os.path.join(TARGET_DIR, f)
        size_mb = os.path.getsize(fpath) / (1024*1024)
        print(f"  {f[:70]} ({size_mb:.1f} MB)")

if __name__ == "__main__":
    main()
