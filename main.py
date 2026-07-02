import os
from google import genai
from pydantic import BaseModel

# Geminiの設定
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

# 台本のデータ構造を定義
class Script(BaseModel):
    title: str
    narration: str
    visual_prompt: str

# 台本生成のリクエスト
response = client.models.generate_content(
    model='gemini-2.0-flash',
    contents="YouTube Shorts用の面白い雑学台本を書いて。JSON形式で出力して。",
    config={
        "response_mime_type": "application/json",
        "response_schema": Script,
    },
)

print(response.text)
