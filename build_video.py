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
OUTPUT_VIDEO_PATH = "output_shorts.mp4"
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
ICON_PATH = "youtubeicon.png"

# 安定動作するニューラル音声リスト（男性・女性を動画ごとにランダム選定）
AVAILABLE_VOICES = [
    "ja-JP-KeitaNeural",   # 落ち着いた男性（解説・暴露向き）
    "ja-JP-NanamiNeural",  # 明瞭な女性アナウンサー声
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


def download_pexels_video(queries: list[str], output_path: str, min_duration: float = 3.0) -> bool:
    """Pexels APIから高画質な縦型動画をダウンロード"""
    if not PEXELS_API_KEY:
        print("⚠️ PEXELS_API_KEY が設定されていません。")
        return False

    api_headers = {
        "Authorization": PEXELS_API_KEY,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }

    for query in queries:
        try:
            url = (
                f"https://api.pexels.com/videos/search?"
                f"query={urllib.parse.quote(query)}&orientation=portrait&per_page=8"
            )
            req = urllib.request.Request(url, headers=api_headers)
            with urllib.request.urlopen(req, timeout=12) as res:
                data = json.loads(res.read().decode("utf-8"))

            videos = data.get("videos", [])
            for v in videos:
                if v.get("duration", 0) < min_duration:
                    continue

                video_files = v.get("video_files", [])
                target_file = None

                for vf in video_files:
                    w = vf.get("width", 0)
                    h = vf.get("height", 0)
                    if h > w and h >= 1280:
                        target_file = vf
                        break

                if not target_file and video_files:
                    target_file = video_files[0]

                if target_file and target_file.get("link"):
                    d_req = urllib.request.Request(
                        target_file["link"],
                        headers={"User-Agent": api_headers["User-Agent"]},
                    )
                    with urllib.request.urlopen(d_req, timeout=30) as d_res, open(output_path, "wb") as f_out:
                        f_out.write(d_res.read())
                    print(f"🎬 Pexels取得成功: '{query}' (長さ: {v.get('duration')}s)")
                    return True

        except Exception as e:
            print(f"⚠️ Pexels取得スキップ (クエリ: '{query}'): {e}")

    return False


def create_solid_fallback_video(duration: float, output_path: str):
    """映像取得が失敗した際の安全なバックアップ背景"""
    clip = ColorClip(size=(VIDEO_WIDTH, VIDEO_HEIGHT), color=(15, 20, 28), duration=duration)
    clip.write_videofile(output_path, fps=24, logger=None)
    clip.close()


async def _synthesize_edge_tts(text: str, target_file: str, voice_name: str, rate: str):
    """edge-tts を用いて高品質なニューラル音声を生成"""
    communicate = edge_tts.Communicate(text, voice_name, rate=rate)
    await communicate.save(target_file)


def generate_audio(
    text: str, output_path: str, voice_name: str, volume_boost: float, voice_rate: str
) -> float:
    """edge-tts で音声を生成し、FFmpeg で音量を増幅して保存"""
    raw_tts_path = f"raw_{output_path}"

    asyncio.run(_synthesize_edge_tts(text, raw_tts_path, voice_name=voice_name, rate=voice_rate))

    cmd = [
        "ffmpeg", "-y", "-i", raw_tts_path,
        "-filter:a", f"volume={volume_boost}",
        "-vn", output_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    if os.path.exists(raw_tts_path):
        os.remove(raw_tts_path)

    audio = AudioFileClip(output_path)
    duration = audio.duration
    audio.close()
    return duration


def render_rich_subtitle_image(
    text: str,
    color_name: str,
    font_size: int,
    use_bg_box: bool,
    bg_opacity: int,
    width: int = VIDEO_WIDTH,
    height: int = 280,
) -> str:
    """フォントサイズ・配色・半透明黒座布団を反映したテロップ画像を生成"""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    color_map = {
        "yellow": (255, 230, 0, 255),
        "white": (255, 255, 255, 255),
        "cyan": (0, 240, 255, 255),
    }
    font_color = color_map.get(color_name, (255, 230, 0, 255))
    outline_color = (0, 0, 0, 255)

    font = get_available_font(size=font_size)

    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    except Exception:
        text_w = min(len(text) * (font_size - 4), width - 60)
        text_h = font_size + 10

    x = max((width - text_w) // 2, 30)
    y = (height - text_h) // 2

    # 半透明の黒帯（座布団）を描画
    if use_bg_box:
        pad_x = 28
        pad_y = 16
        box_coords = [
            x - pad_x,
            y - pad_y,
            x + text_w + pad_x,
            y + text_h + pad_y,
        ]
        draw.rounded_rectangle(
            box_coords, radius=18, fill=(0, 0, 0, int(bg_opacity))
        )

    stroke_width = 6
    try:
        draw.text(
            (x, y),
            text,
            font=font,
            fill=font_color,
            stroke_width=stroke_width,
            stroke_fill=outline_color,
        )
    except Exception:
        for dx in range(-stroke_width, stroke_width + 1):
            for dy in range(-stroke_width, stroke_width + 1):
                if dx * dx + dy * dy <= stroke_width * stroke_width:
                    try:
                        draw.text((x + dx, y + dy), text, font=font, fill=outline_color)
                    except Exception:
                        pass
        try:
            draw.text((x, y), text, font=font, fill=font_color)
        except Exception:
            pass

    out_file = f"sub_{random.randint(1000, 9999)}.png"
    img.save(out_file)
    return out_file


def generate_spectrum_overlay(
    audio_path: str, duration: float, box_size: int, icon_diameter: int, fps: int = 30
) -> ImageSequenceClip:
    """指定サイズに応じたスペクトラムアナライザーを動
