import json
import os
import random
import urllib.parse
import urllib.request
from gtts import gTTS
from moviepy.editor import (
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
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


def generate_audio_gtts(text: str, output_path: str) -> float:
    """gTTSで音声を生成して正確な尺を返す"""
    tts = gTTS(text=text, lang="ja", slow=False)
    tts.save(output_path)
    audio = AudioFileClip(output_path)
    duration = audio.duration
    audio.close()
    return duration


def render_rich_subtitle_image(
    text: str, color_name: str, width: int = VIDEO_WIDTH, height: int = 380
) -> str:
    """日本語フォントで太字・黒縁取りテロップ画像を生成"""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    color_map = {
        "yellow": (255, 230, 0, 255),
        "white": (255, 255, 255, 255),
        "cyan": (0, 240, 255, 255),
    }
    font_color = color_map.get(color_name, (255, 230, 0, 255))
    outline_color = (0, 0, 0, 255)

    font = get_available_font(size=74)

    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    except Exception:
        text_w = min(len(text) * 70, width - 40)
        text_h = 80

    x = max((width - text_w) // 2, 20)
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


def apply_camera_motion(clip: VideoFileClip, motion_type: str) -> VideoFileClip:
    """ズームイン・ズームアウト演出"""
    duration = clip.duration
    if motion_type == "zoom_in":
        return clip.resize(lambda t: 1.0 + 0.15 * (t / duration))
    elif motion_type == "zoom_out":
        return clip.resize(lambda t: 1.15 - 0.15 * (t / duration))
    return clip


def build_single_scene(scene: Scene, index: int) -> VideoFileClip:
    """1シーンの音声・映像・テロップ・トランジションの合成"""
    print(f"\n--- シーン {index + 1} 構築中 ---")
    audio_path = f"temp_voice_{index}.mp3"
    raw_video_path = f"temp_raw_{index}.mp4"

    # 1. 音声生成（シーンの尺は音声の実尺と完全に一致させて範囲外アクセスを防ぐ）
    scene_duration = generate_audio_gtts(scene.narration, audio_path)

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

    # 4. カメラワーク
    base_clip = apply_camera_motion(base_clip, scene.camera_motion)

    # 5. テロップ描画
    sub_img_path = render_rich_subtitle_image(scene.subtitle_text, scene.subtitle_color)
    sub_clip = ImageClip(sub_img_path).set_duration(scene_duration)

    if scene.subtitle_position == "top":
        sub_y = 260
    elif scene.subtitle_position == "center":
        sub_y = (VIDEO_HEIGHT - 380) // 2
    else:
        sub_y = VIDEO_HEIGHT - 480

    sub_clip = sub_clip.set_position(("center", sub_y))

    # 6. 音声とレイヤーの合成（音声尺と映像尺を厳密に一致させる）
    audio_clip = AudioFileClip(audio_path).set_duration(scene_duration)
    layers = [base_clip, sub_clip]

    if scene.screen_effect == "flash":
        flash_clip = (
            ColorClip(size=(VIDEO_WIDTH, VIDEO_HEIGHT), color=(255, 255, 255))
            .set_duration(0.1)
            .set_opacity(0.85)
        )
        layers.append(flash_clip)

    composite = CompositeVideoClip(layers, size=(VIDEO_WIDTH, VIDEO_HEIGHT)).set_duration(scene_duration)
    composite = composite.set_audio(audio_clip)

    if os.path.exists(sub_img_path):
        os.remove(sub_img_path)

    return composite


def build_full_video(script: DetailedScript):
    """全シーンを結合してShorts動画を書き出し"""
    scene_clips = []
    for i, scene_data in enumerate(script.scenes):
        clip = build_single_scene(scene_data, i)
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
    build_full_video(generated_script)
