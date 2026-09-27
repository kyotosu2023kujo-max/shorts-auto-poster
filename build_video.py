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

# --- 定数設定 ---
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
OUTPUT_VIDEO_PATH = "output_shorts.mp4"
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
ICON_PATH = "youtubeicon.png"

# 確実に動作する安定版ニューラル音声リスト（男性・女性の2系統でランダム選定）
AVAILABLE_VOICES = [
    "ja-JP-KeitaNeural",   # 落ち着いた男性（解説・暴露向き）
    "ja-JP-NanamiNeural",  # 明瞭な女性アナウンサー声
]

VOICE_RATE = "+38%"        # 1.4倍速相当のテンポ感
VOICE_VOLUME_BOOST = 1.5   # FFmpegでの音量ブースト（約+3.5dB）


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
    text: str, output_path: str, voice_name: str, volume_boost: float = VOICE_VOLUME_BOOST
) -> float:
    """edge-tts で音声を生成し、FFmpeg で音量を増幅して保存"""
    raw_tts_path = f"raw_{output_path}"

    asyncio.run(_synthesize_edge_tts(text, raw_tts_path, voice_name=voice_name, rate=VOICE_RATE))

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
    text: str, color_name: str, width: int = VIDEO_WIDTH, height: int = 260
) -> str:
    """被りを防ぐため、フォントサイズと描画エリアを最適化したテロップ画像を生成"""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    color_map = {
        "yellow": (255, 230, 0, 255),
        "white": (255, 255, 255, 255),
        "cyan": (0, 240, 255, 255),
    }
    font_color = color_map.get(color_name, (255, 230, 0, 255))
    outline_color = (0, 0, 0, 255)

    font = get_available_font(size=68)

    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    except Exception:
        text_w = min(len(text) * 65, width - 60)
        text_h = 75

    x = max((width - text_w) // 2, 30)
    y = (height - text_h) // 2

    stroke_width = 7
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


def generate_spectrum_overlay(audio_path: str, duration: float, fps: int = 30) -> ImageSequenceClip:
    """左下配置用スペクトラムアナライザー（340px枠）を生成"""
    icon_size = (135, 135)
    if os.path.exists(ICON_PATH):
        icon_raw = Image.open(ICON_PATH).convert("RGBA")
    else:
        icon_raw = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
        draw_ico = ImageDraw.Draw(icon_raw)
        draw_ico.ellipse((5, 5, 155, 155), fill=(0, 200, 255, 255))

    icon_raw = icon_raw.resize(icon_size, Image.Resampling.LANCZOS)
    mask = Image.new("L", icon_size, 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.ellipse((0, 0, icon_size[0], icon_size[1]), fill=255)

    icon_img = Image.new("RGBA", icon_size, (0, 0, 0, 0))
    icon_img.paste(icon_raw, (0, 0), mask)

    y, sr = librosa.load(audio_path)
    hop_length = int(sr / fps)
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]

    if len(rms) > 0 and (np.max(rms) - np.min(rms) > 1e-8):
        rms_normalized = (rms - np.min(rms)) / (np.max(rms) - np.min(rms) + 1e-8)
        rms_boosted = np.power(rms_normalized, 0.4)
    else:
        rms_boosted = np.zeros(int(duration * fps))

    num_bars = 40
    radius_base = 80
    max_bar_length = 55
    box_size = 340
    center_x = box_size / 2
    center_y = box_size / 2

    total_frames = max(len(rms_boosted), int(duration * fps))
    frames = []

    for i in range(total_frames):
        volume = float(rms_boosted[i]) if i < len(rms_boosted) else 0.0
        frame_img = Image.new("RGBA", (box_size, box_size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(frame_img)

        for b in range(num_bars):
            angle = (360 / num_bars) * b
            rad = np.deg2rad(angle)

            bar_len = max(6, int(volume * max_bar_length))
            start_r = radius_base
            end_r = radius_base + bar_len

            start_x = center_x + start_r * np.cos(rad)
            start_y = center_y + start_r * np.sin(rad)
            end_x = center_x + end_r * np.cos(rad)
            end_y = center_y + end_r * np.sin(rad)

            draw.line([(start_x, start_y), (end_x, end_y)], fill=(0, 240, 255, 235), width=4)

        icon_x = center_x - icon_size[0] / 2
        icon_y = center_y - icon_size[1] / 2
        frame_img.paste(icon_img, (int(icon_x), int(icon_y)), icon_img)

        frames.append(np.array(frame_img))

    clip = ImageSequenceClip(frames, fps=fps)
    return clip.set_duration(duration)


def apply_camera_motion(clip: VideoFileClip, motion_type: str) -> VideoFileClip:
    """ズーム演出"""
    duration = clip.duration
    if motion_type == "zoom_in":
        return clip.resize(lambda t: 1.0 + 0.15 * (t / duration))
    elif motion_type == "zoom_out":
        return clip.resize(lambda t: 1.15 - 0.15 * (t / duration))
    return clip


def build_single_scene(scene: Scene, index: int, voice_name: str) -> VideoFileClip:
    """1シーンの合成処理"""
    print(f"\n--- シーン {index + 1} 構築中 (ボイス: {voice_name}) ---")
    audio_path = f"temp_voice_{index}.mp3"
    raw_video_path = f"temp_raw_{index}.mp4"

    # 1. edge-tts で音声生成
    scene_duration = generate_audio(
        scene.narration, audio_path, voice_name=voice_name, volume_boost=VOICE_VOLUME_BOOST
    )

    # 2. 素材動画ダウンロード
    downloaded = download_pexels_video(
        scene.visual_search_queries, raw_video_path, min_duration=scene_duration
    )
    if not downloaded:
        create_solid_fallback_video(scene_duration, raw_video_path)

    # 3. リサイズ＆クロップ（9:16）
    base_clip = VideoFileClip(raw_video_path)
    if base_clip.duration < scene_duration:
        base_clip = vfx.loop(base_clip, duration=scene_duration)
    else:
        base_clip = base_clip.subclip(0, scene_duration)

    base_clip = base_clip.resize(height=VIDEO_HEIGHT)
    if base_clip.w < VIDEO_WIDTH:
        base_clip = base_clip.resize(width=VIDEO_WIDTH)
    base_clip = base_clip.crop(
        x1=(base_clip.w - VIDEO_WIDTH) // 2,
        y1=(base_clip.h - VIDEO_HEIGHT) // 2,
        width=VIDEO_WIDTH,
        height=VIDEO_HEIGHT,
    )

    # 4. カメラモーション
    base_clip = apply_camera_motion(base_clip, scene.camera_motion)

    # 5. 左下配置のスペクトラムアナライザー（Y座標: 1920 - 450 = 1470px 付近に固定）
    spectrum_clip = generate_spectrum_overlay(audio_path, scene_duration)
    spectrum_clip = spectrum_clip.set_position((40, VIDEO_HEIGHT - 450))

    # 6. テロップ描画（アナライザーとの干渉を避けて配置）
    sub_img_path = render_rich_subtitle_image(scene.subtitle_text, scene.subtitle_color)
    sub_clip = ImageClip(sub_img_path).set_duration(scene_duration)

    if scene.subtitle_position == "top":
        sub_y = 280
    elif scene.subtitle_position == "center":
        sub_y = (VIDEO_HEIGHT - 260) // 2
    else:
        # bottom 指定時: アナライザー上端（1470px）より上の安全位置に配置
        sub_y = VIDEO_HEIGHT - 680

    sub_clip = sub_clip.set_position(("center", sub_y))

    # 7. レイヤー合成
    audio_clip = AudioFileClip(audio_path).set_duration(scene_duration)
    layers = [base_clip, spectrum_clip, sub_clip]

    if scene.screen_effect == "flash":
        flash_clip = (
            ColorClip(size=(VIDEO_WIDTH, VIDEO_HEIGHT), color=(255, 255, 255))
            .set_duration(0.08)
            .set_opacity(0.85)
        )
        layers.append(flash_clip)

    composite = CompositeVideoClip(layers, size=(VIDEO_WIDTH, VIDEO_HEIGHT)).set_duration(scene_duration)
    composite = composite.set_audio(audio_clip)

    if os.path.exists(sub_img_path):
        os.remove(sub_img_path)

    return composite


def build_full_video(script: DetailedScript):
    """動画1本単位で音声をランダム決定し、全シーンを結合して書き出し"""
    chosen_voice = random.choice(AVAILABLE_VOICES)
    print(f"\n🎙️ 今回選定されたナレーションボイス: {chosen_voice}")

    scene_clips = []
    for i, scene_data in enumerate(script.scenes):
        clip = build_single_scene(scene_data, i, voice_name=chosen_voice)
        scene_clips.append(clip)

    print("\n🎞 全シーンを結合中...")
    final_video = concatenate_videoclips(scene_clips, method="compose")

    final_video.write_videofile(
        OUTPUT_VIDEO_PATH,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        threads=4,
        preset="fast",
        logger="bar",
    )

    for clip in scene_clips:
        clip.close()
    final_video.close()
    print(f"🎉 Shorts動画の出力が完了しました: {OUTPUT_VIDEO_PATH}")


if __name__ == "__main__":
    generated_script = generate_script()

    final_title = generated_script.title.strip()
    if "#Shorts" not in final_title:
        final_title = f"{final_title} #Shorts"

    with open("title.txt", "w", encoding="utf-8") as f:
        f.write(final_title)
    print(f"📌 アップロード用タイトル決定: {final_title}")

    build_full_video(generated_script)
