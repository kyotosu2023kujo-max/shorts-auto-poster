import os
import json
from google import genai
from openai import OpenAI
from pydantic import BaseModel, Field

# 台本のデータ構造
class Script(BaseModel):
    title: str = Field(description="動画のタイトル")
    narration: str = Field(description="ナレーション原稿")
    visual_prompt: str = Field(description="背景映像の生成プロンプト")

gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
groq_client = OpenAI(
    api_key=os.environ["GROQ_API_KEY"],
    base_url="https://api.groq.com/openai/v1"
)

PROMPT = "YouTube Shorts用の面白い雑学台本を書いて。"

def generate_with_gemini(prompt: str) -> Script | None:
    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": Script,
            },
        )
        # response.parsed が直接 Script インスタンスになります
        if response.parsed:
            return response.parsed
        return Script.model_validate_json(response.text)
    except Exception as e:
        print(f"Gemini失敗: {e}")
        return None

def generate_with_groq(prompt: str) -> Script | None:
    try:
        # beta.chat.completions.parse を使ってスキーマを厳密に保証
        response = groq_client.beta.chat.completions.parse(
            model="llama-3.3-70b-versatile",  # 複雑な構造化出力には 70b もおすすめ
            messages=[
                {"role": "system", "content": "YouTube Shorts向けの台本作成アシスタントです。"},
                {"role": "user", "content": prompt}
            ],
            response_format=Script,
        )
        return response.choices[0].message.parsed
    except Exception as e:
        print(f"Groq失敗: {e}")
        return None

def generate_script(prompt: str) -> Script:
    # 1. まずGeminiを試す
    result = generate_with_gemini(prompt)
    if result:
        return result

    # 2. 失敗時はGroqにフォールバック
    print("Groqにフォールバックします...")
    result = generate_with_groq(prompt)
    if result:
        return result

    raise RuntimeError("GeminiもGroqも失敗しました。")

if __name__ == "__main__":
    script = generate_script(PROMPT)
    print(script.model_dump_json(indent=2))
