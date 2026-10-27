import asyncio
import json
import math
import os
import random
import subprocess
import urllib.parse
import urllib.request
import edge_tts
import librosa
import numpy as np
from moviepy.editor import (
    AudioFileClip,
    ColorClip,
    CompositeVideoClip,
    ImageClip,
    ImageSequenceClip,
    VideoFileClip,
    concatenate_videoclips,
    vfx,
)
from PIL import Image, ImageDraw, ImageFont

from scenario import DetailedScript, Scene, generate_script

# --- 定数・パス設定 ---
CONFIG_FILE = "video_style_config.json"
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "")
OUTPUT_VIDEO_PATH = "output_shorts.mp4"
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
ICON_PATH = "youtubeicon.png"

# 安定動作するニューラル音声リスト（男性・女性を動画ごとにランダム選定）
AVAILABLE_VOICES = [
    "ja-JP-KeitaNeural",   # 落ち着いた男性（解説・暴露向き）
    "ja-JP-NanamiNeural",  # 明瞭な女性アナウンサー声
]

# 抽象フォールバック用キーワード群（テーマがマニアックすぎて全滅したときの保険）
FALLBACK_QUERIES = [
    "dark abstract background",
    "space galaxy mystery",
    "science laboratory motion",
    "microscope cells biology",
    "dramatic cinematic light",
]

# --- 演出設定の読み込み（デフォルト値フォールバック付き） ---
DEFAULT_CONFIG = {
    "voice_rate": "+38%",
    "voice_volume_boost": 1.5,
    "max_cut_duration": 3.0,
    "zoom_ratio": 0.15,
    "font_size": 68,
    "subtitle_y_offset": 680,
    "subtitle_bg_box": True,
    "subtitle_bg_opacity": 180,
    "spectrum_box_size": 340,
    "spectrum_icon_size": 135,
    "spectrum_y_offset": 450,
    "opening_flash_enabled": True,
    "default_subtitle_color": "yellow",
}


def load_style_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                config = {**DEFAULT_CONFIG, **loaded}
                print(f"⚙️ 演出設定 '{CONFIG_FILE}' を適用しました。")
                return config
        except Exception as e:
            print(f"⚠️ 設定ファイル読み込み失敗（デフォルト使用）: {e}")
    return DEFAULT_CONFIG.copy()


CONFIG = load_style_config()


def get_available_font(size: int = 72) -> ImageFont.FreeTypeFont:
    """Linux(Ubuntu)およびmacOS環境で確実に使える日本語フォントを探して返す"""
    font_candidates = [
        "/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf",
        "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    for font_path in font_candidates:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                continue

    local_font = "fallback_font.ttf"
    if not os.path.exists(local_font):
        try:
            url = "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP-Bold.ttf"
            urllib.request.urlretrieve(url, local_font)
        except Exception:
            pass

    if os.path.exists(local_font):
        return ImageFont.truetype(local_font, size)

    return ImageFont.load_default()


# --- 素材動画取得（Pexels & Pixabay ハイブリッド多重フォールバック） ---
def fetch_pexels_video(query: str, orientation: str, min_duration: float = 3.0) -> str:
    """Pexels APIから指定の向きで動画URLを取得"""
    if not PEXELS_API_KEY:
        return ""
    try:
        url = (
            f"https://api.pexels.com/videos/search?"
            f"query={urllib.parse.quote(query)}&orientation={orientation}&per_page=6"
        )
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": PEXELS_API_KEY,
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=8) as res:
            data = json.loads(res.read().decode("utf-8"))

        for v in data.get("videos", []):
            if v.get("duration", 0) < min_duration:
                continue
            video_files = v.get("video_files", [])
            for vf in sorted(video_files, key=lambda x: x.get("width", 0) * x.get("height", 0), reverse=True):
                link = vf.get("link")
                if link:
                    return link
    except Exception as e:
        print(f"⚠️ Pexels取得スキップ ({query}, {orientation}): {e}")
    return ""


def fetch_pixabay_video(query: str, min_duration: float = 3.0) -> str:
    """Pixabay APIからHD動画URLを取得"""
    if not PIXABAY_API_KEY:
        return ""
    try:
        url = (
            f"https://pixabay.com/api/videos/?"
            f"key={PIXABAY_API_KEY}&q={urllib.parse.quote(query)}&per_page=6"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as res:
            data = json.loads(res.read().decode("utf-8"))

        for hit in data.get("hits", []):
            if hit.get("duration", 0) < min_duration:
                continue
            videos = hit.get("videos", {})
            for quality in ["large", "medium", "small"]:
                link = videos.get(quality, {}).get("url")
                if link:
                    return link
    except Exception as e:
        print(f"⚠️ Pixabay取得スキップ ({query}): {e}")
    return ""


def download_file(url: str, output_path: str) -> bool:
    """URLからファイルをダウンロードする"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as res:
            with open(output_path, "wb") as f:
                f.write(res.read())
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception as e:
        print(f"⚠️ ダウンロード失敗 ({url}): {e}")
        return False


def download_best_video(queries: list[str], output_path: str, min_duration: float = 3.0) -> bool:
    """複数のクエリと多重フォールバック（Pexels縦・横、Pixabay）を試して動画をダウンロードする"""
    # 1. 縦長動画を優先してPexelsで検索
    for q in queries:
        link = fetch_pexels_video(q, "portrait", min_duration)
        if link:
            if download_file(link, output_path):
                return True

    # 2. 横長動画をPexelsで検索
    for q in queries:
        link = fetch_pexels_video(q, "landscape", min_duration)
        if link:
            if download_file(link, output_path):
                return True

    # 3. Pixabayで検索
    for q in queries:
        link = fetch_pixabay_video(q, min_duration)
        if link:
            if download_file(link, output_path):
                return True

    # 4. 全滅した場合はフォールバック用キーワードで再試行
    for q in FALLBACK_QUERIES:
        link = fetch_pexels_video(q, "portrait", min_duration)
        if link:
            if download_file(link, output_path):
                return True

    return False
