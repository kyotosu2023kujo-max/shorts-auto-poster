import os
import json
import time
import random
from typing import List, Literal
from google import genai
from openai import OpenAI
from pydantic import BaseModel, Field

# --- テーマをリスト化してランダムに選ぶ ---
THEMES = [
    "深海生物の異常な生存戦略",
    "日常に潜む量子力学の不思議",
    "宇宙空間で起きる物理法則のバグ",
    "植物が身を削って行う恐るべき化学攻撃",
    "歴史に埋もれた狂気の科学実験",
    "昆虫たちの残酷で合理的な寄生・洗脳メカニズム",
    "人間の体内で起きている信じられない細胞の戦い",
    "地球外生命体が存在するかもしれない極限環境の科学"
]
current_theme = random.choice(THEMES)

# シーン（カット）単位の詳細データ構造
class Scene(BaseModel):
    narration: str = Field(description="このシーンで読み上げるナレーション原稿")
    subtitle_text: str = Field(description="画面に大きく表示する強調テロップ（10〜15文字程度）")
    visual_search_query: str = Field(description="Pexels検索用の英語キーワード（例: 'cut watermelon summer', 'galaxy stars'）")
    subtitle_position: Literal["top", "center", "bottom"] = Field(default="bottom", description="テロップの表示位置")
    subtitle_color: Literal["yellow", "white", "cyan"] = Field(default="yellow", description="テロップの文字色")
    motion_effect: Literal["zoom_in", "zoom_out", "static"] = Field(default="zoom_in", description="カメラワーク演出（ズームイン、ズームアウト、固定）")

# 全体台本
class DetailedScript(BaseModel):
    title: str = Field(description="動画全体のフックになるタイトル（常時上部表示）")
    scenes: List[Scene] = Field(description="3〜5つのシーンに分割された台本リスト")

gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
groq_client = OpenAI(
    api_key=os.environ["GROQ_API_KEY"],
    base_url="https://api.groq.com/openai/v1"
)

# f文字列のまま、JSONのフォーマット（{}はエスケープのために二重にしています）を追加します
PROMPT = f"""#依頼内容
あなたは、科学史や専門知識に精通したリサーチャー・構成作家です。YouTube Shorts向けの知的好奇心を刺激するマニアックな雑学動画の台本と詳細な映像演出構成を作成してください。
また、専門性とエンタメ性を両立したコンテンツを目指して、センセーショナルに取り上げてください。SNSでのバズりを完全に熟知し、語り口調にこのチャンネル特有の尖りを出して欲しいです。
# 条件
1. シーン構成: 視聴者を飽きさせないよう、テンポの良い4つのシーン（カット）に分割してください。動画の最後には、動画へのいいねとチャンネルの登録の催促、このチャンネルはどのようなチャンネルなのか視聴者に呼びかけてください。
2. 情報の深さ（重要）: 
 - 一般的な「誰でも知っている表面的なまとめ」は禁止です。
 - クマムシ、テッポウエビ、シュレディンガーの猫など、ネットでよく擦られている有名ネタは絶対に避けてください。
 - 具体的な【固有名詞（品種名、専門用語、人名など）】や【歴史的背景・科学的メカニズム】に必ず踏み込んでください。
3. タイトル: 全角15〜20文字以内で作成してください。
4. 映像演出: 各シーンの `visual_search_query` は、Pexelsで確実にヒットする具体的な英語名詞（2〜3単語）にしてください。

# 必須出力フォーマット（厳守）
以下のJSON構造に厳密に従って出力してください。キー名（narrationなど）は絶対に変更しないでください。
{{
  "title": "動画のタイトル",
  "scenes": [
    {{
      "narration": "このシーンで読み上げるナレーション原稿",
      "subtitle_text": "画面に大きく表示する強調テロップ",
      "visual_search_query": "Pexels検索用の英語キーワード",
      "subtitle_position": "bottom",
      "subtitle_color": "yellow",
      "motion_effect": "zoom_in"
    }},
    {{
      "narration": "次のシーンのナレーション...",
      "subtitle_text": "...",
      "visual_search_query": "...",
      "subtitle_position": "center",
      "subtitle_color": "white",
      "motion_effect": "static"
    }}
  ]
}}

# 今回のテーマ
[{current_theme}]"""

def generate_with_gemini(prompt: str, max_retries: int = 3) -> DetailedScript | None:
    for attempt in range(max_retries):
        try:
            response = gemini_client.models.generate_content(
                model="gemini-3.6-flash", # 存在しない3.6から安定版の1.5に修正
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
