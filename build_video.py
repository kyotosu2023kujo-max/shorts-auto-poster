import os
import random
import urllib.parse
import urllib.request
import numpy as np
from gtts import gTTS
from moviepy.editor import (
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
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
FONT_PATH = "/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf"  # Ubuntu環境用日本語フォント


def download_pexels_video(queries: list[str], output_path: str, min_duration: float = 3.0) -> bool:
    """複数のクエリ候補から条件に合う高画質・縦型動画を探してダウンロード"""
    if not PEXELS_API_KEY:
        print("⚠️ PEXELS_API_KEY が設定されていません。")
        return False

    for query in queries:
        try:
            url = (
                f"https://api.pexels.com/videos/search?"
                f"query={urllib.parse.quote(query)}&orientation=portrait&per_page=8"
            )
            req = urllib.request.Request(url, headers={"Authorization": PEXELS_API_KEY})
            with urllib.request.urlopen(req, timeout=10) as res:
                data = json.loads(res.read().decode("utf-8"))

            videos = data.get("videos", [])
            for v in videos:
                if v.get("duration", 0) < min_duration:
                    continue

                video_files = v.get("video_files", [])
                # 縦型HD解像度（1080x1920前後）を優先検索
                target_file = None
                for vf in video_files:
                    if vf.get("width") and vf.get("height"):
                        if vf["height"] > vf["width"] and vf["height"] >= 1280:
                            target_file = vf
                            break

                if not target_file and video_files:
                    target_file = video_files[0]

                if target_file and target_file.get("link"):
                    urllib.request.urlretrieve(target_file["link"], output_path)
                    print(f"🎬 動画ダウンロード成功: クエリ='{query}', 長さ={v.get('duration')}s")
                    return True

        except Exception as e:
            print(f"⚠️ Pexels取得スキップ (クエリ: '{query}'): {e}")

    return False


def create_solid_fallback_video(duration: float, output_path: str):
    """Pexels取得全滅時のバックアップ背景"""
    clip = ColorClip(size=(VIDEO_WIDTH, VIDEO_HEIGHT), color=(15, 18, 25), duration=duration)
    clip.write_videofile(output_path, fps=24, logger=None)
    clip.close()


def generate_audio_gtts(text: str, output_path: str) -> float:
    """gTTSで日本語音声を合成して長さを返す"""
    tts = gTTS(text=text, lang="ja", slow=False)
    tts.save(output_path)
    audio = AudioFileClip(output_path)
    duration = audio.duration
    audio.close()
    return duration


def render_rich_subtitle_image(
    text: str, color_name: str, width: int = VIDEO_WIDTH, height: int = 350
) -> str:
    """PILを用いて太字・黒縁取り・高コントラストなテロップ画像を生成"""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    color_map = {
        "yellow": (255, 230, 0, 255),
        "white": (255, 255, 255, 255),
        "cyan": (0, 240, 255, 255),
    }
    font_color = color_map.get(color_name, (255, 230, 0, 255))
    outline_color = (0, 0, 0, 255)

    try:
        font = ImageFont.truetype(FONT_PATH, 76)
    except Exception:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    x = (width - text_w) // 2
    y = (height - text_h) // 2

    # 縁取りの描画（太さ6px）
    stroke_width = 7
    for dx in range(-stroke_width, stroke_width + 1):
        for dy in range(-stroke_width, stroke_width + 1):
            if dx * dx + dy * dy <= stroke_width * stroke_width:
                draw.text((x + dx, y + dy), text, font=font, fill=outline_color)

    # 本文の描画
    draw.text((x, y), text, font=font, fill=font_color)

    out_file = f"subtitle_{random.randint(1000, 9999)}.png"
    img.save(out_file)
    return out_file


def apply_camera_motion(clip: VideoFileClip, motion_type: str) -> VideoFileClip:
    """滑らかなズームイン/ズームアウト等のカメラ演出"""
    duration = clip.duration

    if motion_type == "zoom_in":
        # 1.0倍から1.15倍へ滑らかに拡大
        return clip.resize(lambda t: 1.0 + 0.15 * (t / duration))
    elif motion_type == "zoom_out":
        # 1.15倍から1.0倍へ縮小
        return clip.resize(lambda t: 1.15 - 0.15 * (t / duration))
    return clip


def build_single_scene(scene: Scene, index: int) -> VideoFileClip:
    """1シーン分の映像・音声・演出・テロップを合成"""
    print(f"\n--- シーン {index + 1} 構築中 ---")
    audio_path = f"temp_voice_{index}.mp3"
    raw_video_path = f"temp_raw_{index}.mp4"

    # 1. 音声生成
    duration = generate_audio_gtts(scene.narration, audio_path)
    # ナレーション終わりに0.4秒の余白を付与
    scene_duration = duration + 0.4

    # 2. 動画ダウンロード（複数候補から厳選）
    download_success = download_pexels_video(scene.visual_search_queries, raw_video_path, min_duration=scene_duration)
    if not download_success:
        create_solid_fallback_video(scene_duration, raw_video_path)

    # 3. 映像のリサイズと尺合わせ
    base_clip = VideoFileClip(raw_video_path)
    if base_clip.duration < scene_duration:
        base_clip = vfx.loop(base_clip, duration=scene_duration)
    else:
        base_clip = base_clip.subclip(0, scene_duration)

    # 画面サイズ調整（9:16にクロップ＆リサイズ）
    base_clip = base_clip.resize(height=VIDEO_HEIGHT)
    if base_clip.w < VIDEO_WIDTH:
        base_clip = base_clip.resize(width=VIDEO_WIDTH)
    base_clip = base_clip.crop(
        x1=(base_clip.w - VIDEO_WIDTH) // 2,
        y1=(base_clip.h - VIDEO_HEIGHT) // 2,
        width=VIDEO_WIDTH,
        height=VIDEO_HEIGHT,
    )

    # 4. カメラ演出
    base_clip = apply_camera_motion(base_clip, scene.camera_motion)

    # 5. テロップ合成
    sub_img_path = render_rich_subtitle_image(scene.subtitle_text, scene.subtitle_color)
    sub_clip = ImageClip(sub_img_path).set_duration(scene_duration)

    # テロップ位置計算
    if scene.subtitle_position == "top":
        sub_y = 250
    elif scene.subtitle_position == "center":
        sub_y = (VIDEO_HEIGHT - 350) // 2
    else:
        sub_y = VIDEO_HEIGHT - 480

    sub_clip = sub_clip.set_position(("center", sub_y))

    # 6. 音声とレイヤーの合成
    audio_clip = AudioFileClip(audio_path)
    layers = [base_clip, sub_clip]

    # フラッシュ演出（画面転換時に白クリップを一瞬重ねる）
    if scene.screen_effect == "flash":
        flash_clip = (
            ColorClip(size=(VIDEO_WIDTH, VIDEO_HEIGHT), color=(255, 255, 255))
            .set_duration(0.12)
            .set_opacity(0.8)
        )
        layers.append(flash_clip)

    composite = CompositeVideoClip(layers, size=(VIDEO_WIDTH, VIDEO_HEIGHT))
    composite = composite.set_audio(audio_clip).set_duration(scene_duration)

    # 一時画像の掃除
    if os.path.exists(sub_img_path):
        os.remove(sub_img_path)

    return composite


def build_full_video(script: DetailedScript):
    """全シーンを結合して最終動画を出力"""
    scene_clips = []
    for i, scene_data in enumerate(script.scenes):
        clip = build_single_scene(scene_data, i)
        scene_clips.append(clip)

    print("\n🎞 全シーンを連結してエンコード中...")
    final_video = concatenate_videoclips(scene_clips, method="compose")

    # YouTube Shorts推奨フォーマットで出力
    final_video.write_videofile(
        OUTPUT_VIDEO_PATH,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        threads=4,
        preset="fast",
        logger="bar",
    )

    # クリーンアップ
    for clip in scene_clips:
        clip.close()
    final_video.close()
    print(f"🎉 動画生成完了: {OUTPUT_VIDEO_PATH}")


if __name__ == "__main__":
    import json
    # 台本生成を実行して動画を構築
    generated_script = generate_script()
    build_full_video(generated_script)
