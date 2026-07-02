import os
import time
from google import genai
from google.genai import errors
from pydantic import BaseModel

# Geminiの設定
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

# 台本のデータ構造を定義
class Script(BaseModel):
    title: str
    narration: str
    visual_prompt: str

def generate_script(prompt: str, model: str = "gemini-2.0-flash", max_retries: int = 3):
    """クォータ超過(429)時にリトライ・フォールバックする生成関数"""
    fallback_models = [model, "gemini-1.5-flash"]  # ダメだったら別モデルも試す

    for candidate_model in fallback_models:
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=candidate_model,
                    contents=prompt,
                    config={
                        "response_mime_type": "application/json",
                        "response_schema": Script,
                    },
                )
                return response.text
            except errors.ClientError as e:
                if e.code == 429:
                    wait = 45 * (attempt + 1)  # 徐々に待ち時間を延ばす
                    print(f"[{candidate_model}] クォータ超過。{wait}秒待って再試行します... ({attempt+1}/{max_retries})")
                    time.sleep(wait)
                else:
                    raise  # 429以外のエラーはそのまま投げる
        print(f"[{candidate_model}] リトライ上限に達したため、次のモデルを試します。")

    raise RuntimeError("すべてのモデル・リトライで失敗しました。クォータ設定を確認してください。")


# 台本生成のリクエスト
result = generate_script("YouTube Shorts用の面白い雑学台本を書いて。JSON形式で出力して。")
print(result)
