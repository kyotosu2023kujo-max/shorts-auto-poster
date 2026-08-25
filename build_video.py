import os
import requests
import asyncio
from moviepy import AudioFileClip, ImageClip, TextClip, CompositeVideoClip
import edge_tts

from scenario import generate_script, Script, PROMPT

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")

# 1. 無料音声合成 (edge-tts: Nanami または Keita)
async def generate_audio_async(text: str, output_path: str = "narration.mp3") -> str:
    communicate = edge_tts.Communicate(text, "ja-JP-NanamiNeural")
    await communicate.save(output_path)
    return output_path

def generate_audio(text: str, output_path: str = "narration.mp3") -> str:
    return asyncio.run(generate_audio_async(text, output_path))

# 2. Pexels から高品質な縦型背景写真を無料ダウンロード
def fetch_background_image(query: str, output_path: str = "background.jpg") -> str:
    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/v1/search?query={query}&orientation=portrait&per_page=1"
    
    response = requests.get(url, headers=headers)
    data = response.json()

    if data.get("photos"):
        # 最も解像度の高い縦長画像のURLを取得
        image_url = data["photos"][0]["src"]["large2x"]
        img_data = requests.get(image_url).content
        with open(output_path, "wb") as f:
            f.write(img_data)
        return output_path
    
    # 見つからなかった場合のフォールバック（美しい風景素材の固定URL）
    fallback_url = "https://images.pexels.com/photos/1624496/pexels-photo-1624496.jpeg"
    img_data = requests.get(fallback_url).content
    with open(output_path, "wb") as f:
        f.write(img_data)
    return output_path

# 3. 動画合成 (MoviePy)
def create_shorts_video(script: Script, audio_path: str, image_path: str, output_path: str = "output_shorts.mp4"):
    audio_clip = AudioFileClip(audio_path)
    duration = audio_clip.duration

    # 背景画像（1080x1920 にリサイズ）
    image_clip = (
        ImageClip(image_path)
        .with_duration(duration)
        .resized((1080, 1920))
    )

    # タイトルテロップ（日本語フォント + 縁取り）
    txt_clip = (
        TextClip(
            text=script.title,
            font_size=52,
            color='yellow',
            stroke_color='black',
            stroke_width=3,
            font='/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
            size=(960, None),
            method='caption'
        )
        .with_position(('center', 250))
        .with_duration(duration)
    )

    video = CompositeVideoClip([image_clip, txt_clip]).with_audio(audio_clip)
    video.write_videofile(
        output_path,
        fps=30,
        codec="libx264",
        audio_codec="aac"
    )

    audio_clip.close()
    video.close()

if __name__ == "__main__":
    print("1. 台本を生成中...")
    script = generate_script(PROMPT)
    print(f"タイトル: {script.title}")

    print("2. 音声を生成中 (edge-tts)...")
    audio_path = generate_audio(script.narration)

    print("3. 背景素材を取得中 (Pexels)...")
    # visual_prompt または 英語キーワードで検索
    image_path = fetch_background_image(script.visual_prompt)

    print("4. 動画を合成・書き出し中...")
    create_shorts_video(script, audio_path, image_path, "output_shorts.mp4")
    print("動画生成が完了しました！")
