import os
import requests
import asyncio
from moviepy import (
    AudioFileClip,
    ImageClip,
    TextClip,
    CompositeVideoClip,
    concatenate_videoclips,
    vfx
)
import edge_tts
from scenario import generate_script, DetailedScript, Scene

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
FONT_PATH = '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'

# 音声生成
async def generate_scene_audio(text: str, output_path: str) -> str:
    communicate = edge_tts.Communicate(text, "ja-JP-NanamiNeural")
    await communicate.save(output_path)
    return output_path

# 背景画像取得
def fetch_scene_image(query: str, output_path: str) -> str:
    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/v1/search?query={query}&orientation=portrait&per_page=1"
    response = requests.get(url, headers=headers)
    data = response.json()

    if data.get("photos"):
        image_url = data["photos"][0]["src"]["large2x"]
        img_data = requests.get(image_url).content
        with open(output_path, "wb") as f:
            f.write(img_data)
        return output_path

    # フォールバック画像
    fallback_url = "https://images.pexels.com/photos/1624496/pexels-photo-1624496.jpeg"
    with open(output_path, "wb") as f:
        f.write(requests.get(fallback_url).content)
    return output_path

# シーン動画の組み立て
def build_scene_clip(scene: Scene, index: int) -> CompositeVideoClip:
    audio_path = f"audio_{index}.mp3"
    image_path = f"image_{index}.jpg"

    # 1. 音声と画像
    asyncio.run(generate_scene_audio(scene.narration, audio_path))
    fetch_scene_image(scene.visual_search_query, image_path)

    audio_clip = AudioFileClip(audio_path)
    duration = audio_clip.duration

    # 2. 画像クリップと動き（ズームイン/ズームアウト演出）
    base_img = (
        ImageClip(image_path)
        .with_duration(duration)
        .resized((1080, 1920))
    )

    if scene.motion_effect == "zoom_in":
        # 時間経過で 1.0倍 -> 1.15倍 に拡大
        base_img = base_img.with_effects([vfx.Resize(lambda t: 1 + 0.05 * t)])
    elif scene.motion_effect == "zoom_out":
        base_img = base_img.with_effects([vfx.Resize(lambda t: 1.15 - 0.05 * t)])

    # 3. テロップ位置のマッピング
    pos_map = {
        "top": ("center", 350),
        "center": ("center", 900),
        "bottom": ("center", 1450)
    }
    pos = pos_map.get(scene.subtitle_position, ("center", 1450))

    # 4. 字幕テロップ
    txt_clip = (
        TextClip(
            text=scene.subtitle_text,
            font_size=64,
            color=scene.subtitle_color,
            stroke_color='black',
            stroke_width=4,
            font=FONT_PATH,
            size=(950, None),
            method='caption'
        )
        .with_position(pos)
        .with_duration(duration)
    )

    return CompositeVideoClip([base_img, txt_clip], size=(1080, 1920)).with_audio(audio_clip)

def build_full_video(script: DetailedScript, output_path: str = "output_shorts.mp4"):
    scene_clips = []
    
    print(f"🎬 全 {len(script.scenes)} シーンの動画を生成中...")
    for i, scene in enumerate(script.scenes):
        print(f"  - シーン {i+1} 構築中: {scene.subtitle_text} (Effect: {scene.motion_effect})")
        clip = build_scene_clip(scene, i)
        scene_clips.append(clip)

    # 全シーンを順番に結合
    final_video = concatenate_videoclips(scene_clips, method="compose")

    # 常時表示のヘッダータイトルバー
    title_header = (
        TextClip(
            text=f"【{script.title}】",
            font_size=42,
            color='white',
            stroke_color='black',
            stroke_width=3,
            font=FONT_PATH,
            size=(1000, None),
            method='caption'
        )
        .with_position(('center', 120))
        .with_duration(final_video.duration)
    )

    full_composite = CompositeVideoClip([final_video, title_header], size=(1080, 1920))
    
    full_composite.write_videofile(
        output_path,
        fps=30,
        codec="libx264",
        audio_codec="aac"
    )

    full_composite.close()

if __name__ == "__main__":
    script = generate_script()
    build_full_video(script, "output_shorts.mp4")
    audio_path = generate_audio(script.narration)

    print("3. 背景素材を取得中 (Pexels)...")
    # visual_prompt または 英語キーワードで検索
    image_path = fetch_background_image(script.visual_prompt)

    print("4. 動画を合成・書き出し中...")
    create_shorts_video(script, audio_path, image_path, "output_shorts.mp4")
    print("動画生成が完了しました！")
