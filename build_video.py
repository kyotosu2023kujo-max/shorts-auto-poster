import os
import requests
from openai import OpenAI
from moviepy import AudioFileClip, ImageClip, TextClip, CompositeVideoClip
from pydantic import BaseModel

openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

class Script(BaseModel):
    title: str
    narration: str
    visual_prompt: str

# 1. 音声合成 (OpenAI TTS 例: VOICEVOX / ElevenLabs も同様に差し替え可能)
def generate_audio(text: str, output_path: str = "narration.mp3") -> str:
    response = openai_client.audio.speech.create(
        model="tts-1",
        voice="alloy",
        input=text
    )
    response.stream_to_file(output_path)
    return output_path

# 2. 背景画像生成 (DALL-E 3: 縦長 1024x1792)
def generate_image(prompt: str, output_path: str = "background.png") -> str:
    response = openai_client.images.generate(
        model="dall-e-3",
        prompt=f"YouTube Shorts vertical background, high quality, vibrant: {prompt}",
        size="1024x1792",
        n=1
    )
    image_url = response.data[0].url
    img_data = requests.get(image_url).content
    with open(output_path, "wb") as f:
        f.write(img_data)
    return output_path

# 3. 動画・字幕・音声の結合 (MoviePy)
def create_shorts_video(script: Script, audio_path: str, image_path: str, output_path: str = "output_shorts.mp4"):
    # 音声クリップをロードして長さを取得
    audio_clip = AudioFileClip(audio_path)
    duration = audio_clip.duration

    # 背景画像クリップ（動画の縦横比 1080x1920 にリサイズ）
    image_clip = (
        ImageClip(image_path)
        .set_duration(duration)
        .resize((1080, 1920))
    )

    # タイトル / テロップ
    txt_clip = (
        TextClip(
            script.title,
            fontsize=64,
            color='white',
            font='Arial-Bold',
            stroke_color='black',
            stroke_width=3,
            size=(900, None),
            method='caption'
        )
        .set_position(('center', 250))
        .set_duration(duration)
    )

    # 合成して書き出し
    video = CompositeVideoClip([image_clip, txt_clip]).set_audio(audio_clip)
    video.write_videofile(
        output_path,
        fps=30,
        codec="libx264",
        audio_codec="aac"
    )

    # リソース解放
    audio_clip.close()
    video.close()
