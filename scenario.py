import os
import json
import time
import random
from typing import List, Literal
from google import genai
from openai import OpenAI
from pydantic import BaseModel, Field
import gspread
from google.oauth2.service_account import Credentials

# --- Googleスプレッドシート設定 ---
# サービスアカウントのJSONファイル名とスプレッドシート名（またはID）を指定
CREDENTIALS_FILE = "credentials.json"
SPREADSHEET_NAME = "YouTube_Shorts_History"

def get_past_themes() -> List[str]:
    """スプレッドシートから過去のテーマ一覧を取得する"""
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
        gc = gspread.authorize(creds)
        sheet = gc.open(SPREADSHEET_NAME).sheet1
        # 2列目（テーマ列）を想定して取得（1行目はヘッダー）
        themes = sheet.col_values(2)[1:] 
        return themes
    except Exception as e:
        print(f"⚠️ スプレッドシートからの履歴取得に失敗しました（初回は無視して続行します）: {e}")
        return []

def append_to_sheet(theme: str, title: str):
    """生成成功したテーマとタイトルをスプレッドシートに追記する"""
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
        gc = gspread.authorize(creds)
        sheet = gc.open(SPREADSHEET_NAME).sheet1
        # [日時, テーマ, タイトル] の形式で追記
        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([now, theme, title])
        print("📝 スプレッドシートに履歴を保存しました。")
    except Exception as e:
        print(f"⚠️ スプレッドシートへの書き込みに失敗しました: {e}")

# --- テーマの選定と重複回避 ---
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

past_themes = get_past_themes()
# 過去に選ばれたテーマを候補から除外
available_themes = [t for t in THEMES if t not in past_themes]

if not available_themes:
    print("すべてのテーマを消化しました。候補リストをリセットします。")
    available_themes = THEMES

current_theme = random.choice(available_themes)

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

# 過去の履歴をプロンプトに組み込んで重複した切り口を防ぐ
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

# 過去に扱ったテーマ（※これらと重複する切り口や具体例は絶対に避けてください）
{json.dumps(past_themes, ensure_ascii=False)}

# 今回のテーマ
[{current_theme}]
"""

def generate_with_gemini(prompt: str, max_retries: int = 3) -> DetailedScript | None:
    for attempt in range(max_retries):
        try:
            response = gemini_client.models.generate_content(
                model="gemini-1.5-flash",
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
    # 動画生成パイプラインの成功時に以下を実行してスプレッドシートに記録する
    append_to_sheet(current_theme, script.title)
