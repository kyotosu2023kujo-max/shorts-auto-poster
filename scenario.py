import json
import os
import random
import time
from datetime import datetime
from typing import List, Literal, Tuple

from google import genai
from pydantic import BaseModel, Field

# --- ローカル履歴管理設定 ---
HISTORY_FILE = "history.json"

# 大テーマ候補
THEMES = [
    "深海生物の異常な生存戦略",
    "日常に潜む量子力学の不思議",
    "宇宙空間で起きる物理法則のバグ",
    "植物が身を削って行う恐るべき化学攻撃",
    "歴史に埋もれた狂気の科学実験",
    "昆虫たちの残酷で合理的な寄生・洗脳メカニズム",
    "人間の体内で起きている信じられない細胞の戦い",
    "地球外生命体が存在するかもしれない極限環境の科学",
]

# マンネリ防止用アングル（毎回ランダム適用）
PERSPECTIVE_ANGLES = [
    "学会や常識を覆した狂気の逆転劇・パラドックス",
    "分子・ナノレベルの精密すぎる残酷な物理・生化学トラップ",
    "人類の倫理観や直感を完全に粉砕するグロテスクな合理的システム",
    "教科書には絶対に載せられない、実験の失敗・副作用がもたらした怪現象",
    "一見すると弱点に見える性質が、実は極限の武器へと昇華された瞬間",
]

# --- 履歴管理関数 ---
def load_history() -> Tuple[List[str], List[str]]:
    """ローカルの history.json から過去のテーマ一覧とタイトル一覧を取得"""
    if not os.path.exists(HISTORY_FILE):
        return [], []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            records = json.load(f)
            past_themes = [r.get("theme", "") for r in records if r.get("theme")]
            past_titles = [f"【{r.get('theme')}】{r.get('title')}" for r in records if r.get("title")]
            return past_themes, past_titles
    except Exception as e:
        print(f"⚠️ 履歴ファイルの読み込みに失敗しました（初回として処理します）: {e}")
        return [], []

def save_record(theme: str, title: str):
    """生成成功したテーマとタイトルを history.json に保存"""
    records = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                records = json.load(f)
        except Exception:
            records = []

    records.append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "theme": theme,
        "title": title
    })

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"📝 '{HISTORY_FILE}' に生成履歴を追記しました。")

# --- データスキーマ定義 ---
class Scene(BaseModel):
    narration: str = Field(description="このシーンで読み上げるナレーション原稿（尖った語り口調）")
    subtitle_text: str = Field(description="画面に大きく表示する強調テロップ（10〜15文字程度）")
    visual_search_query: str = Field(description="Pexels検索用の具体的な英語キーワード（2〜3単語）")
    subtitle_position: Literal["top", "center", "bottom"] = Field(default="bottom", description="テロップ表示位置")
    subtitle_color: Literal["yellow", "white", "cyan"] = Field(default="yellow", description="テロップ文字色")
    motion_effect: Literal["zoom_in", "zoom_out", "static"] = Field(default="zoom_in", description="カメラワーク")

class DetailedScript(BaseModel):
    title: str = Field(description="動画全体のフックになるタイトル（全角15〜20文字以内）")
    scenes: List[Scene] = Field(min_length=4, max_length=4, description="テンポの良い4つのシーン構成")

# --- プロンプト構築 ---
def build_prompt(current_theme: str, angle: str, past_titles: List[str]) -> str:
    # 直近の重複を避けるため過去タイトル（最大15件）を禁止リストとして注入
    recent_history = past_titles[-15:] if len(past_titles) > 15 else past_titles

    return f"""# 依頼内容
あなたは、科学史や専門知識に精通したリサーチャー兼構成作家です。
YouTube Shorts向けの知的好奇心を刺激するマニアックな雑学動画の台本と演出構成を作成してください。
SNSで指を止めさせるため、冷笑的かつセンセーショナルで尖った語り口調を採用してください。

# 重要要件
1. シーン構成: テンポの良い4つのシーン（カット）で構成してください。動画のラスト（第4シーンの最後）で、視聴者に自然な形で動画への高評価とチャンネル登録を促してください。
2. ネタの差別化（最重要）:
   - 一般的な「ネットのまとめ記事」にある定番ネタ（クマムシ、デメニギス、テッポウエビ、シュレディンガーの猫、ウーパールーパー等）は完全禁止です。
   - 【具体的な固有名詞（生物の学名・種名、化合物の正式名称、提唱した学者名など）】と【極小・極限の具体的メカニズム】を必ず主役に据えてください。
3. タイトル: 全角15〜20文字以内で、タイムラインで異彩を放つフックのあるもの。
4. 映像演出: 各シーンの `visual_search_query` は、Pexelsの実写動画ライブラリで確実にヒットする英語名詞（2〜3単語）にしてください。

# 過去に作成した動画タイトル一覧（※これらで扱った具体的な生物・実験・切り口との重複は厳禁）
{json.dumps(recent_history, ensure_ascii=False, indent=2)}

# 今回のテーマ
【テーマ】: {current_theme}
【必須アプローチ・切り口】: {angle}
※上記の「必須アプローチ」に沿った、意外性のある題材を1つ厳選して掘り下げてください。
"""

# --- Gemini API 呼び出し ---
def generate_with_gemini(prompt: str, max_retries: int = 3) -> DetailedScript:
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))
    gemini_models = ["gemini-3.7-flash", "gemini-3.8-flash"]

    last_error = None
    for attempt in range(max_retries):
        model_name = gemini_models[attempt % len(gemini_models)]
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": DetailedScript,
                    "temperature": 1.0,
                    "seed": random.randint(1, 10000000),
                },
            )
            if response.parsed:
                return response.parsed
            return DetailedScript.model_validate_json(response.text)
        except Exception as e:
            last_error = e
            print(f"Gemini({model_name}) 試行 {attempt + 1}/{max_retries} 失敗: {e}")
            if attempt < max_retries - 1:
                time.sleep(3 * (attempt + 1))

    raise RuntimeError(f"台本生成に失敗しました: {last_error}")

def main():
    # 1. 過去履歴の取得
    past_themes, past_titles = load_history()

    # 2. テーマ選定（未消化のものを優先、全て消化したらリセット）
    available_themes = [t for t in THEMES if t not in past_themes]
    if not available_themes:
        print("🔄 全テーマを消化したため、テーマ選定をリセットします。")
        available_themes = THEMES

    current_theme = random.choice(available_themes)
    selected_angle = random.choice(PERSPECTIVE_ANGLES)
    print(f"🎯 選定テーマ: {current_theme}")
    print(f"🔍 適用アングル: {selected_angle}")

    # 3. 台本生成
    prompt = build_prompt(current_theme, selected_angle, past_titles)
    script = generate_with_gemini(prompt)

    # 4. 結果表示
    print("\n=== 生成された台本 ===")
    print(script.model_dump_json(indent=2))

    # 5. ローカルの history.json に保存
    save_record(current_theme, script.title)

if __name__ == "__main__":
    main()
