import os
import requests
from openai import OpenAI
from moviepy import AudioFileClip, ImageClip, TextClip, CompositeVideoClip
from pydantic import BaseModel

# scenario.py から台本生成関数とクラスをインポート
from scenario import generate_script, Script, PROMPT

openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

def generate_audio(text: str, output_path: str = "narration.mp3") -> str:
    response = openai_client.audio.speech.create(
        model="tts-1",
        voice="alloy",
        input=text
    )
    response.stream_to_file(output_path)
    return output_path

def generate_image(prompt: str, output_path: str = "background.png") -> str:
    response = openai_client.images.generate(
        model="dall-e-3",
        prompt=f"YouTube Shorts vertical background, 9:16 aspect ratio, high quality: {prompt}",
        size="1024x1792",
        n=1
    )
    image_url = response.data[0].url
    img_data = requests.get(image_url).content
    with open(output_path, "wb") as f:
        f.write(img_data)
    return output_path

def create_shorts_video(script: Script, audio_path: str, image_path: str, output_path: str = "output_shorts.mp4"):
    audio_clip = AudioFileClip(audio_path)
    duration = audio_clip.duration

    image_clip = (
        ImageClip(image_path)
        .with_duration(duration)
        .resized((1080, 1920))
    )

    txt_clip = (
        TextClip(
            text=script.title,
            font_size=60,
            color='white',
            stroke_color='black',
            stroke_width=3,
            size=(900, None),
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

# --- ここから実行部を追加 ---
if __name__ == "__main__":
    print("1. 台本を生成中...")
    script = generate_script(PROMPT)
    print(f"生成されたタイトル: {script.title}")

    print("2. 音声を生成中...")
    audio_path = generate_audio(script.narration)

    print("3. 画像を生成中...")
    image_path = generate_image(script.visual_prompt)

    print("4. 動画を合成・書き出し中...")
    create_shorts_video(script, audio_path, image_path, "output_shorts.mp4")
    print("動画生成が完了しました！")
