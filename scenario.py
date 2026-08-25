import os
import json
import time
from google import genai
from openai import OpenAI
from pydantic import BaseModel, Field

# 台本のデータ構造
class Script(BaseModel):
    title: str = Field(description="動画のタイトル")
    narration: str = Field(description="ナレーション原稿")
    visual_prompt: str = Field(description="背景映像の検索用英語キーワード（例: galaxy star space background）")

gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
groq_client = OpenAI(
    api_key=os.environ["GROQ_API_KEY"],
    base_url="https://api.groq.com/openai/v1"
)

PROMPT = "YouTube Shorts用の面白い雑学台本を書いて。visual_promptはPexels検索に使えるシンプルな英語キーワードにして。"

def generate_with_gemini(prompt: str, max_retries: int = 3) -> Script | None:
    for attempt in range(max_retries):
        try:
            response = gemini_client.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": Script,
                },
            )
            if response.parsed:
                return response.parsed
            return Script.model_validate_json(response.text)
        except Exception as e:
            print(f"Gemini試行 {attempt + 1}/{max_retries} 失敗: {e}")
            if attempt < max_retries - 1:
                time.sleep(3)  # 503等のスパイク時は少し待機してリトライ
    return None

def generate_with_groq(prompt: str) -> Script | None:
    try:
        # 現行のGroq対応モデル (openai/gpt-oss-20b)
        response = groq_client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "system", "content": "必ずJSON形式のみで出力してください。title, narration, visual_promptの3つのキーを含めること。"},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content)
        return Script(**data)
    except Exception as e:
        print(f"Groq失敗: {e}")
        return None

def generate_script(prompt: str) -> Script:
    # 1. まずGeminiを試す (リトライ付き)
    result = generate_with_gemini(prompt)
    if result:
        return result

    # 2. ダメならGroqにフォールバック
    print("Groqにフォールバックします...")
    result = generate_with_groq(prompt)
    if result:
        return result

    raise RuntimeError("GeminiもGroqも失敗しました。")

if __name__ == "__main__":
    script = generate_script(PROMPT)
    print(script.model_dump_json(indent=2))
