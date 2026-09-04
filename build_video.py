import os
import requests
import asyncio
import numpy as np
import librosa
import soundfile as sf
from moviepy import (
    AudioFileClip,
    ImageClip,
    VideoClip,
    CompositeVideoClip,
    CompositeAudioClip,
    concatenate_videoclips,
    vfx
)
import edge_tts
from scenario import generate_script, DetailedScript, Scene
from PIL import Image, ImageDraw, ImageFont

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
FONT_PATH = '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'

def generate_text_image(text: str, font_path: str, font_size: int, max_width: int, output_path: str, text_color: str):
    try:
        font = ImageFont.truetype(font_path, size=font_size, index=0)
    except OSError:
        print(f"⚠️ フォント読み込みエラー: {font_path}")
        return None

    lines = []
    current_line = ""
    
    for char in text:
        if char == '\n':
            lines.append(current_line)
            current_line = ""
            continue
        
        test_line = current_line + char
        width = font.getlength(test_line)
        
        if width <= max_width:
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = char
            
    if current_line:
        lines.append(current_line)

    ascent, descent = font.getmetrics()
    line_height = ascent + descent
    bottom_padding = int(descent * 1.5)
    total_height = (line_height * len(lines)) + bottom_padding

    img = Image.new('RGBA', (max_width, total_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    y_text = 0
    for line in lines:
        line_width = font.getlength(line)
        x_offset = (max_width - line_width) / 2
        draw.text((x_offset, y_text), line, font=font, fill=text_color)
        y_text += line_height

    img.save(output_path)
    return output_path

async def generate_scene_audio(text: str, output_path: str) -> str:
    temp_path = output_path.replace(".wav", "_temp.mp3")
    # 1.5倍速 (rate="+50%")
    communicate = edge_tts.Communicate(text, "ja-JP-NanamiNeural", rate="+50%")
    await communicate.save(temp_path)
    
    # 前後の無音をトリミング
    y, sr = librosa.load(temp_path, sr=None)
    trimmed_y, _ = librosa.effects.trim(y, top_db=25)
    
    sf.write(output_path, trimmed_y, sr)
    
    if os.path.exists(temp_path):
        os.remove(temp_path)
        
    return output_path

def fetch_scene_image(query: str, output_path: str) -> str:
    success = False
    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/v1/search?query={query}&orientation=portrait&per_page=1"
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        if data.get("photos") and len(data["photos"]) > 0:
            image_url = data["photos"][0]["src"]["large2x"]
            img_data = requests.get(image_url, timeout=10).content
            with open(output_path, "wb") as f:
                f.write(img_data)
            success = True
    except Exception:
        pass

    if success:
        try:
            with Image.open(output_path) as img:
                img = img.convert('RGB')
                img.save(output_path, "JPEG")
                return output_path
        except Exception:
            success = False

    print(f"⚠️ 画像取得に失敗したため、安全な背景画像を自動生成します: {query}")
    img = Image.new('RGB', (1080, 1920), color=(15, 23, 42))
    img.save(output_path, "JPEG")
    return output_path

def create_spectrum_videoclip(audio_path: str, duration: float, fps: int, icon_path: str) -> VideoClip:
    y, sr = librosa.load(audio_path)
    hop_length = int(sr / fps)
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    
    rms_normalized = (rms - np.min(rms)) / (np.max(rms) - np.min(rms) + 1e-8)
    rms_boosted = np.power(rms_normalized, 0.5)

    icon_img = None
    icon_size = (130, 130)
    if os.path.exists(icon_path):
        try:
            icon_raw = Image.open(icon_path).convert('RGBA')
            icon_raw = icon_raw.resize(icon_size, Image.Resampling.LANCZOS)
            mask = Image.new('L', icon_size, 0)
            draw_mask = ImageDraw.Draw(mask)
            draw_mask.ellipse((0, 0, icon_size[0], icon_size[1]), fill=255)
            icon_img = Image.new('RGBA', icon_size, (0, 0, 0, 0))
            icon_img.paste(icon_raw, (0, 0), mask)
        except OSError:
            print(f"⚠️ アイコン読み込みエラー: {icon_path}")

    num_bars = 48
    radius_base = 75
    max_bar_length = 45

    def make_frame(t):
        frame_idx = min(int(t * fps), len(rms_boosted) - 1)
        volume = rms_boosted[frame_idx]

        comp_img = Image.new('RGBA', (340, 340), (0, 0, 0, 0))
        draw = ImageDraw.Draw(comp_img)
        center_x, center_y = 170.0, 170.0

        for b in range(num_bars):
            angle = (360 / num_bars) * b
            rad = np.deg2rad(angle)
            bar_len = max(4, int(volume * max_bar_length))
            
            start_x = center_x + radius_base * np.cos(rad)
            start_y = center_y + radius_base * np.sin(rad)
            end_x = center_x + (radius_base + bar_len) * np.cos(rad)
            end_y = center_y + (radius_base + bar_len) * np.sin(rad)
            
            alpha = int(180 + volume * 75)
            draw.line([(start_x, start_y), (end_x, end_y)], fill=(0, 220, 255, alpha), width=3)

        if icon_img:
            icon_x = int(center_x - icon_size[0] / 2)
            icon_y = int(center_y - icon_size[1] / 2)
            comp_img.paste(icon_img, (icon_x, icon_y), icon_img)

        return np.array(comp_img)

    return VideoClip(make_frame, duration=duration, is_mask=False)

def build_scene_clip_with_spectrum(scene: Scene, index: int) -> CompositeVideoClip:
    audio_path = f"audio_{index}.wav"
    image_path = f"image_{index}.jpg"
    icon_path = "youtubeicon.png"
    
    asyncio.run(generate_scene_audio(scene.narration, audio_path))
    fetch_scene_image(scene.visual_search_query, image_path)
    
    if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
        raise RuntimeError(f"音声ファイルの生成に失敗しました: {audio_path}")
    if not os.path.exists(image_path) or os.path.getsize(image_path) < 100:
        raise RuntimeError(f"画像ファイルの取得に失敗しました: {image_path}")

    audio_clip = AudioFileClip(audio_path)
    duration = audio_clip.duration
    fps = 30

    base_img = (
        ImageClip(image_path)
        .with_duration(duration)
        .resized((1080, 1920))
    )
    if scene.motion_effect == "zoom_in":
        base_img = base_img.with_effects([vfx.Resize(lambda t: 1 + 0.04 * t)])
    elif scene.motion_effect == "zoom_out":
        base_img = base_img.with_effects([vfx.Resize(lambda t: 1.15 - 0.04 * t)])

    # --- アイコンと字幕の配置・衝突判定 ---
    icon_x = 50
    icon_y = 1300      # アイコンは常に左下の位置に固定
    icon_height = 340

    y_pos_map = {
        "top": 350,
        "center": 900,
        "bottom": 1450
    }
    y_pos = y_pos_map.get(scene.subtitle_position, 1450)

    # 字幕ボックスの上下Y座標
    sub_top = y_pos - 20
    sub_bottom = sub_top + 160

    # アイコンと字幕ボックスの縦方向が被っているかを判定
    is_overlapping = not (icon_y + icon_height < sub_top or icon_y > sub_bottom)

    if is_overlapping:
        # 被る場合は【文字（字幕）】を上に避ける（アイコンの上に配置）
        y_pos = 1050

    # 字幕背景ボックスの生成
    box_img = Image.new("RGBA", (1000, 160), (0, 0, 0, 160))
    box_path = f"box_{index}.png"
    box_img.save(box_path)
    bg_box = ImageClip(box_path).with_duration(duration).with_position(('center', y_pos - 20))

    # 字幕テキストの生成
    txt_path = f"text_{index}.png"
    generate_text_image(
        text=scene.subtitle_text,
        font_path=FONT_PATH,
        font_size=65,
        max_width=950,
        output_path=txt_path,
        text_color=scene.subtitle_color
    )
    txt_clip = ImageClip(txt_path).with_position(('center', y_pos)).with_duration(duration)

    # スペクトラムアイコンクリップの生成と配置
    animated_spectrum = create_spectrum_videoclip(audio_path, duration, fps, icon_path)
    animated_spectrum = animated_spectrum.with_position((icon_x, icon_y))

    return CompositeVideoClip([base_img, bg_box, txt_clip, animated_spectrum], size=(1080, 1920)).with_audio(audio_clip)

def build_full_video(script: DetailedScript, output_path: str = "output_shorts.mp4"):
    scene_clips = []
    
    print(f"🎬 全 {len(script.scenes)} シーンの動画を生成中...")
    for i, scene in enumerate(script.scenes):
        print(f"  - シーン {i+1} 構築中: {scene.subtitle_text}")
        clip = build_scene_clip_with_spectrum(scene, i)
        scene_clips.append(clip)

    main_video = concatenate_videoclips(scene_clips, method="compose")

    raw_title = script.title
    if not raw_title.startswith("【"):
        raw_title = f"【{raw_title}】"

    title_box_img = Image.new("RGBA", (1060, 140), (0, 0, 0, 190))
    title_box_path = "title_box.png"
    title_box_img.save(title_box_path)

    title_bg = (
        ImageClip(title_box_path)
        .with_duration(main_video.duration)
        .with_position(('center', 120))
    )

    title_text_path = "title_text.png"
    generate_text_image(
        text=raw_title,
        font_path=FONT_PATH,
        font_size=48,
        max_width=1000,
        output_path=title_text_path,
        text_color='#FFD700'
    )

    title_header = (
        ImageClip(title_text_path)
        .with_position(('center', 135))
        .with_duration(main_video.duration)
    )

    final_video = CompositeVideoClip([main_video, title_bg, title_header], size=(1080, 1920))

    if os.path.exists("bgm.mp3"):
        bgm_clip = AudioFileClip("bgm.mp3").multiply_volume(0.12).with_duration(final_video.duration)
        final_audio = CompositeAudioClip([final_video.audio, bgm_clip])
        final_video = final_video.with_audio(final_audio)

    final_video.write_videofile(
        output_path,
        fps=30,
        codec="libx264",
        audio_codec="aac"
    )

    final_video.close()

def validate_script_quality(script) -> bool:
    for i, scene in enumerate(script.scenes):
        text_len = len(scene.subtitle_text)
        if text_len > 38:
            print(f"❌ シーン {i+1} の文字数が多すぎます（{text_len}文字）。ボツにします。")
            return False
    
    if len(script.title) > 30:
        print(f"❌ タイトルが長すぎます（{len(script.title)}文字）。ボツにします。")
        return False

    return True

if __name__ == "__main__":
    max_retries = 3
    success = False  # ← これが抜けていたため NameError が発生していました

    for attempt in range(1, max_retries + 1):
        print(f"\n🔄 【品質チェック付き生成ループ】 試行回数: {attempt}/{max_retries}")
        
        try:
            script = generate_script()
            
            if not validate_script_quality(script):
                print("🔄 条件に満たなかったため、新しいシナリオで作り直します...")
                continue
            
            print("✅ シナリオの品質チェック合格！動画のビルドを開始します。")
            build_full_video(script, "output_shorts.mp4")
            
            def upload_to_tmp_storage(file_path: str) -> str:
    """完成した動画を一時ファイル共有サービスにアップロードしてURLを発行する"""
    try:
        url = "https://file.io"
        with open(file_path, "rb") as f:
            response = requests.post(url, files={"file": f}, data={"expires": "1d"})
        res_data = response.json()
        if res_data.get("success"):
            return res_data.get("link")
    except Exception as e:
        print(f"⚠️ 一時URLの発行に失敗しました: {e}")
    return None
