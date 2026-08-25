import os
import json
import time
from typing import List, Literal
from google import genai
from openai import OpenAI
from pydantic import BaseModel, Field

# シーン（カット）単位の詳細データ構造
class Scene(BaseModel):
    narration: str = Field(description="このシーンで読み上げるナレーション原稿")
    subtitle_text: str = Field(description="画面に大きく表示する強調テロップ（10〜15文字程度）")
    visual_search_query: str = Field(description="Pexels検索用の英語キーワード（例: 'cut watermelon summer', 'galaxy stars'）")
    subtitle_position: Literal["top", "center", "bottom"] = Field(
        default="bottom",
        description="テロップの表示位置"
    )
    subtitle_color: Literal["yellow", "white", "cyan"] = Field(
        default="yellow",
        description="テロップの文字色"
    )
    motion_effect: Literal["zoom_in", "zoom_out", "static"] = Field(
        default="zoom_in",
        description="カメラワーク演出（ズームイン、ズームアウト、固定）"
    )

# 全体台本
class DetailedScript(BaseModel):
    title: str = Field(description="動画全体のフックになるタイトル（常時上部表示）")
    scenes: List[Scene] = Field(description="3〜5つのシーンに分割された台本リスト")

gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
groq_client = OpenAI(
    api_key=os.environ["GROQ_API_KEY"],
    base_url="https://api.groq.com/openai/v1"
)

PROMPT = """YouTube Shorts向けの面白い雑学動画の台本と詳細な映像演出を作成してください。
視聴者を飽きさせないよう、3〜5個のテンポの良いシーン（カット）に分割してください。
各シーンの visual_search_query はPexelsで確実にヒットする具体的な英語名詞（2〜3単語）にしてください。"""

def generate_with_gemini(prompt: str, max_retries: int = 3) -> DetailedScript | None:
    for attempt in range(max_retries):
        try:
            response = gemini_client.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": DetailedScript,
                },
            )
            if response.parsed:
                return response.parsed
            return DetailedScript.model_validate_json(response.text)
        except Exception as e:
            print(f"Gemini試行 {attempt + 1}/{max_retries} 失敗: {e}")
            if attempt < max_retries - 1:
                time.sleep(3)
    return None

def generate_with_groq(prompt: str) -> DetailedScript | None:
    try:
        response = groq_client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "system", "content": "必ず指定されたスキーマのJSON形式のみで出力してください。"},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content)
        return DetailedScript(**data)
    except Exception as e:
        print(f"Groq失敗: {e}")
        return None

def generate_script(prompt: str = PROMPT) -> DetailedScript:
    result = generate_with_gemini(prompt)
    if result:
        return result

    print("Groqにフォールバックします...")
    result = generate_with_groq(prompt)
    if result:
        return result

    raise RuntimeError("GeminiもGroqも失敗しました。")

if __name__ == "__main__":
    script = generate_script()
    print(script.model_dump_json(indent=2))
        return result

    raise RuntimeError("GeminiもGroqも失敗しました。")

if __name__ == "__main__":
    script = generate_script(PROMPT)
    print(script.model_dump_json(indent=2))
