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
    for q in queries:
        link = fetch_pexels_video(q, "portrait", min_duration)
        if link:
            if download_file(link, output_path):
                return True

    for q in queries:
        link = fetch_pexels_video(q, "landscape", min_duration)
        if link:
            if download_file(link, output_path):
                return True

    for q in queries:
        link = fetch_pixabay_video(q, min_duration)
        if link:
            if download_file(link, output_path):
                return True

    for q in FALLBACK_QUERIES:
        link = fetch_pexels_video(q, "portrait", min_duration)
        if link:
            if download_file(link, output_path):
                return True

    return False


async def generate_voice(text: str, output_path: str, voice: str) -> float:
    """Edge TTSを使用して音声を生成し、音声の長さを秒数で返す"""
    communicate = edge_tts.Communicate(text, voice, rate=CONFIG["voice_rate"])
    await communicate.save(output_path)
    
    y, sr = librosa.load(output_path, sr=None)
    duration = librosa.get_duration(y=y, sr=sr)
    return duration


def create_text_image(text: str, font: ImageFont.FreeTypeFont, text_color="yellow", bg_box=True) -> Image.Image:
    """字幕用のテキスト画像を生成する"""
    padding_x = 30
    padding_y = 20
    
    dummy_img = Image.new("RGBA", (1080, 300), (0, 0, 0, 0))
    draw = ImageDraw.Draw(dummy_img)
    
    lines = text.split("\n")
    max_w = 0
    total_h = 0
    line_heights = []
    
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        max_w = max(max_w, w)
        line_heights.append(h)
        total_h += h + 10

    img_w = max_w + padding_x * 2
    img_h = total_h + padding_y * 2
    
    img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    if bg_box:
        opacity = CONFIG["subtitle_bg_opacity"]
        draw.rounded_rectangle(
            [(0, 0), (img_w, img_h)],
            radius=15,
            fill=(0, 0, 0, opacity)
        )
        
    y_text = padding_y
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x_text = (img_w - w) // 2
        
        for adj_x in [-3, 0, 3]:
            for adj_y in [-3, 0, 3]:
                draw.text((x_text + adj_x, y_text + adj_y), line, font=font, fill=(0, 0, 0, 255))
        
        draw.text((x_text, y_text), line, font=font, fill=text_color)
        y_text += line_heights[i] + 10
        
    return img


async def build_main():
    print("🎬 ショート動画の自動生成を開始します...")
    
    # pending_scenario.json が存在すればそれを優先的に読み込む
    scenario_file = "pending_scenario.json"
    if os.path.exists(scenario_file):
        print(f"📖 '{scenario_file}' から編集済み台本を読み込んでいます...")
        try:
            with open(scenario_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            script = DetailedScript(**data)
        except Exception as e:
            print(f"⚠️ 編集済み台本の読み込みに失敗しました ({e})。新規生成にフォールバックします。")
            script = generate_script()
    else:
        print("⚠️ pending_scenario.json が見つからないため、新規生成します...")
        script = generate_script()

    print(f"📝 タイトル: {script.title}")
    print(f"📝 シーン数: {len(script.scenes)}")
    
    selected_voice = random.choice(AVAILABLE_VOICES)
    print(f"🗣️ 使用音声: {selected_voice}")
    
    scene_clips = []
    audio_clips = []
    
    temp_files = []
    
    try:
        for i, scene in enumerate(script.scenes):
            print(f"--- シーン {i+1}/{len(script.scenes)} 処理中 ---")
            
            audio_path = f"temp_audio_{i}.mp3"
            temp_files.append(audio_path)
            duration = await generate_voice(scene.narration, audio_path, selected_voice)
            
            video_path = f"temp_video_{i}.mp4"
            temp_files.append(video_path)
            
            # 正しい属性名 visual_search_queries を使用
            queries = scene.visual_search_queries if scene.visual_search_queries else [script.title]
            success = download_best_video(queries, video_path, min_duration=2.0)
            
            if not success or not os.path.exists(video_path):
                print(f"⚠️ シーン {i+1} の素材取得に失敗。単色背景にフォールバックします。")
                bg_clip = ColorClip(size=(VIDEO_WIDTH, VIDEO_HEIGHT), color=(20, 20, 30), duration=duration)
            else:
                v_clip = VideoFileClip(video_path)
                if v_clip.duration < duration:
                    n_loops = math.ceil(duration / v_clip.duration)
                    v_clip = v_clip.fx(vfx.loop, n=n_loops)
                
                v_clip = v_clip.subclip(0, duration)
                
                w, h = v_clip.size
                target_aspect = VIDEO_WIDTH / VIDEO_HEIGHT
                current_aspect = w / h
                
                if current_aspect > target_aspect:
                    new_h = VIDEO_HEIGHT
                    new_w = int(new_h * current_aspect)
                    v_clip = v_clip.resize(height=new_h)
                    x_center = new_w // 2
                    v_clip = v_clip.crop(x1=x_center - VIDEO_WIDTH//2, y1=0, x2=x_center + VIDEO_WIDTH//2, y2=VIDEO_HEIGHT)
                else:
                    new_w = VIDEO_WIDTH
                    new_h = int(new_w / current_aspect)
                    v_clip = v_clip.resize(width=new_w)
                    y_center = new_h // 2
                    v_clip = v_clip.crop(x1=0, y1=y_center - VIDEO_HEIGHT//2, x2=VIDEO_WIDTH, y2=y_center + VIDEO_HEIGHT//2)
                
                bg_clip = v_clip
            
            a_clip = AudioFileClip(audio_path)
            
            font = get_available_font(CONFIG["font_size"])
            text_img = create_text_image(scene.subtitle_text, font, text_color=CONFIG["default_subtitle_color"], bg_box=CONFIG["subtitle_bg_box"])
            
            img_path = f"temp_sub_{i}.png"
            temp_files.append(img_path)
            text_img.save(img_path)
            
            txt_clip = ImageClip(img_path).set_duration(duration)
            txt_clip = txt_clip.set_position(("center", CONFIG["subtitle_y_offset"]))
            
            video_with_text = CompositeVideoClip([bg_clip, txt_clip]).set_duration(duration)
            scene_clips.append(video_with_text)
            audio_clips.append(a_clip)
            
        print("🔗 すべてのシーンを結合中...")
        final_video = concatenate_videoclips(scene_clips, method="compose")
        
        from moviepy.editor import concatenate_audioclips
        final_audio = concatenate_audioclips(audio_clips)
        
        final_video = final_video.set_audio(final_audio)
        
        print(f"💾 動画を書き出し中: {OUTPUT_VIDEO_PATH}")
        final_video.write_videofile(
            OUTPUT_VIDEO_PATH,
            fps=30,
            codec="libx264",
            audio_codec="aac",
            bitrate="4M",
            preset="medium",
            threads=4
        )
        
        print("✨ 動画生成が正常に完了しました！")
        
    finally:
        for f in temp_files:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass


if __name__ == "__main__":
    asyncio.run(build_main())
    
    if not os.path.exists(OUTPUT_VIDEO_PATH) or os.path.getsize(OUTPUT_VIDEO_PATH) == 0:
        print("❌ エラー: 動画の生成に失敗しました ('output_shorts.mp4' が存在しません)。")
        exit(1)
