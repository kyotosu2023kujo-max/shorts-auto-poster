import os
import requests
import asyncio
import numpy as np
import librosa
from moviepy import (
    AudioFileClip,
    ImageClip,
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

# ==========================================
# Pillowを使ったテキスト画像生成（見切れ防止対応）
# ==========================================
def generate_text_image(text: str, font_path: str, font_size: int, max_width: int, output_path: str, text_color: str):
    """
    指定幅で自動折返しを行い、下部の見切れを防ぐパディングを追加した透過PNGを生成する
    """
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

# ==========================================
# 音声生成
# ==========================================
async def generate_scene_audio(text: str, output_path: str) -> str:
    communicate = edge_tts.Communicate(text, "ja-JP-NanamiNeural")
    await communicate.save(output_path)
    return output_path

# ==========================================
# 背景画像取得（Wikimedia優先、Pexelsフォールバック）
# ==========================================
def fetch_wikimedia_image(query: str, output_path: str) -> bool:
    url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrnamespace": 6,
        "gsrsearch": query,
        "gsrlimit": 1,
        "prop": "imageinfo",
        "iiprop": "url"
    }
    headers = {"User-Agent": "CuriosityScienceBot/1.0 (Educational YouTube Project)"}
    
    try:
        response = requests.get(url, params=params, headers=headers)
        data = response.json()
        pages = data.get("query", {}).get("pages", {})
        
        for page_id, page_info in pages.items():
            imageinfo = page_info.get("imageinfo", [])
            if imageinfo:
                img_url = imageinfo[0].get("url")
                if img_url:
                    img_data = requests.get(img_url, headers=headers).content
                    with open(output_path, "wb") as f:
                        f.write(img_data)
                    print(f"博物・学術画像をWikimedia Commonsから取得: {query}")
                    return True
    except Exception as e:
        print(f"Wikimedia Commons取得エラー: {e}")
        
    return False

def fetch_scene_image(query: str, output_path: str) -> str:
    if fetch_wikimedia_image(query, output_path):
        return output_path

    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/v1/search?query={query}&orientation=portrait&per_page=1"
    
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        if data.get("photos") and len(data["photos"]) > 0:
            image_url = data["photos"][0]["src"]["large2x"]
            img_data = requests.get(image_url).content
            with open(output_path, "wb") as f:
                f.write(img_data)
            print(f"Pexelsから画像を取得: {query}")
            return output_path
    except Exception as e:
        print(f"Pexels画像取得エラー: {e}")

    fallback_url = "https://images.pexels.com/photos/1624496/pexels-photo-1624496.jpeg"
    with open(output_path, "wb") as f:
        f.write(requests.get(fallback_url).content)
    return output_path

# ==========================================
# 円形スペクトラムアナライザー生成関数
# ==========================================
def generate_circular_spectrum_frames(audio_path: str, duration: float, fps: int, icon_path: str, output_folder: str):
    """
    音声ボリュームに合わせて脈動する円形スペクトラムを生成し、連番PNGとして保存する
    """
    y, sr = librosa.load(audio_path)
    hop_length = int(sr / fps)
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    
    rms_normalized = (rms - np.min(rms)) / (np.max(rms) - np.min(rms) + 1e-8)
    rms_boosted = np.power(rms_normalized, 0.5)
    
    try:
        icon_img = Image.open(icon_path).convert('RGBA')
        icon_size = icon_img.size
    except OSError:
        print(f"⚠️ アイコン読み込みエラー: {icon_path}")
        return []

    spectrum_clips = []
    num_bars = 64
    radius_base = 110
    max_bar_length = 70
    
    os.makedirs(output_folder, exist_ok=True)

    for i, volume in enumerate(rms_boosted):
        if i >= len(rms_boosted):
             break
             
        comp_img = Image.new('RGBA', (400, 400), (0, 0, 0, 0))
        draw = ImageDraw.Draw(comp_img)
        
        center_x = comp_img.width / 2
        center_y = comp_img.height / 2

        for b in range(num_bars):
            angle = (360 / num_bars) * b
            rad = np.deg2rad(angle)
            
            bar_len = max(5, int(volume * max_bar_length))
            
            start_r = radius_base
            end_r = radius_base + bar_len
            
            start_x = center_x + start_r * np.cos(rad)
            start_y = center_y + start_r * np.sin(rad)
            end_x = center_x + end_r * np.cos(rad)
            end_y = center_y + end_r * np.sin(rad)
            
            bar_width = 4
            alpha = int(150 + volume * 100)
            bar_color = (0, 200, 255, alpha)
            
            draw.line([(start_x, start_y), (end_x, end_y)], fill=bar_color, width=bar_width)

        icon_x = center_x - icon_size[0] / 2
        icon_y = center_y - icon_size[1] / 2
        comp_img.paste(icon_img, (int(icon_x), int(icon_y)), icon_img)

        frame_path = os.path.join(output_folder, f"spectrum_frame_{i}.png")
        comp_img.save(frame_path)
        spectrum_clips.append(ImageClip(frame_path).with_duration(1/fps))

    return spectrum_clips

# ==========================================
# シーン動画の組み立て（スペクトラム合成を追加）
# ==========================================
def build_scene_clip_with_spectrum(scene: Scene, index: int) -> CompositeVideoClip:
    audio_path = f"audio_{index}.mp3"
    image_path = f"image_{index}.jpg"
    icon_path = "youtubeicon.png"
    spec_output_folder = f"spectrum_frames_{index}"
    asyncio.run(generate_scene_audio(scene.narration, audio_path))
    fetch_scene_image(scene.visual_search_query, image_path)
    
    # 👇 ここから追加：ファイルが正常に生成されているかチェック
    if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
        raise RuntimeError(f"音声ファイルの生成に失敗しました: {audio_path}")
    if not os.path.exists(image_path) or os.path.getsize(image_path) < 100:
        raise RuntimeError(f"画像ファイルの取得に失敗しました: {image_path}")
    # 👆 ここまで追加

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

    y_pos_map = {
        "top": 350,
        "center": 900,
        "bottom": 1450
    }
    y_pos = y_pos_map.get(scene.subtitle_position, 1450)

    box_img = Image.new("RGBA", (1000, 160), (0, 0, 0, 160))
    box_path = f"box_{index}.png"
    box_img.save(box_path)
    bg_box = ImageClip(box_path).with_duration(duration).with_position(('center', y_pos - 20))

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

    spectrum_clips = generate_circular_spectrum_frames(audio_path, duration, fps, icon_path, spec_output_folder)
    
    if spectrum_clips:
        animated_spectrum = concatenate_videoclips(spectrum_clips).with_duration(duration)
        animated_spectrum = animated_spectrum.with_position((340, 1450)) # 画面上の配置位置
        return CompositeVideoClip([base_img, bg_box, txt_clip, animated_spectrum], size=(1080, 1920)).with_audio(audio_clip)
    else:
        return CompositeVideoClip([base_img, bg_box, txt_clip], size=(1080, 1920)).with_audio(audio_clip)

# ==========================================
# 全体動画の合成とレンダリング
# ==========================================
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
    success = False

    for attempt in range(1, max_retries + 1):
        print(f"\n🔄 【品質チェック付き生成ループ】 試行回数: {attempt}/{max_retries}")
        
        try:
            script = generate_script()
            
            if not validate_script_quality(script):
                print("🔄 条件に満たなかったため、新しいシナリオで作り直します...")
                continue
            
            print("✅ シナリオの品質チェック合格！動画のビルドを開始します。")
            build_full_video(script, "output_shorts.mp4")
            
            success = True
            print("🎉 完璧な品質の動画が完成しました！")
            
            with open("title.txt", "w", encoding="utf-8") as f:
                f.write(script.title)
            print(f"📝 タイトルを保存しました: {script.title}")

            break
            
        except Exception as e:
            print(f"⚠️ 構築中にエラーが発生しました: {e}")
            print("🔄 エラーが発生したため再試行します...")

    if not success:
        print("❌ 最大試行回数に達しましたが、合格する動画を作れませんでした。")
        exit(1)
