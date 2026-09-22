import json
import os
import random
import time
from datetime import datetime
from typing import Dict, List, Literal, Tuple

from google import genai
from pydantic import BaseModel, Field

# --- 設定 ---
HISTORY_FILE = "history.json"
SYSTEM_PROMPT_FILE = "system_prompt.txt"

# 収益性・エンゲージメント重視のジャンル群
PROFIT_THEMES = [
    "知らないと損する金の裏ルール",
    "人間関係を一瞬で破壊する心理トラップ",
    "男女の無意識な本音と行動心理",
    "有名企業の誰も言わない闇と儲けのカラクリ",
    "日常に潜む合法的な搾取の仕組み",
    "SNSやネットで隠蔽された身近な怪事件",
    "脳科学が証明した成功者の異常な思考習慣",
    "一般人が一生気付かない法律・制度の抜け穴",
    "身近なヒット商品の狂気的なマーケティング戦略",
    "知ると人間不信になる進化心理学の真実",
]

# 高維持率・スワイプ防止のための構成アングル
PROFIT_ANGLES = [
    "冒頭1秒で『あなたは搾取されている』と突きつける損失回避フック",
    "常識を180度ひっくり返してコメント欄を議論で燃えさせる逆説提示",
    "具体的な金額・確率・年数を提示して現実感を殴りつける数字フック",
    "『これを知らない人は全員損してます』という強烈な限定感の付与",
    "ラストのオチが冒頭のセリフに自然に繋がる無限ループ構造",
]


# --- 拡張版 履歴・メトリクス管理 ---
def load_history_with_metrics() -> Tuple[List[Dict], List[Dict]]:
    """過去の投稿実績から成功動画（High）と低迷動画（Low）を抽出"""
    if not os.path.exists(HISTORY_FILE):
        return [], []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            records = json.load(f)
            evaluated = [r for r in records if "views" in r and r.get("views") is not None]
            if not evaluated:
                return records, []

            evaluated.sort(
                key=lambda x: (x.get("views", 0) * (x.get("retention", 0.5) + 0.5)),
                reverse=True,
            )
            top_performers = evaluated[:3]
            worst_performers = evaluated[-3:] if len(evaluated) >= 6 else []
            return top_performers, worst_performers
    except Exception as e:
        print(f"⚠️ 履歴読み込みスキップ: {e}")
        return [], []


def save_initial_record(theme: str, angle: str, title: str):
    """動画生成直後のメタデータを保存"""
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
        "angle": angle,
        "title": title,
        "views": None,
        "retention": None,
        "likes": None,
        "comments": None,
    })

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"📝 投稿メタデータを '{HISTORY_FILE}' に保存しました。")


# --- データスキーマ定義 ---
class Scene(BaseModel):
    narration: str = Field(
        description="ナレーション。無駄な前置きを排除し、早口で情報を畳み掛ける構成（1シーンあたり25〜45文字程度）"
    )
    subtitle_text: str = Field(
        description="画面中央〜下に大きく表示する強烈なテロップ（8〜12文字程度）"
    )
    visual_search_queries: List[str] = Field(
        min_length=2,
        max_length=3,
        description="Pexels検索用キーワード候補。感情や緊張感を煽る実写映像（例: ['counting money dark', 'stressed businessman', 'airport window rain']）",
    )
    camera_motion: Literal["zoom_in", "zoom_out", "static"] = Field(default="zoom_in")
    screen_effect: Literal["none", "flash"] = Field(default="none")
    subtitle_position: Literal["top", "center", "bottom"] = Field(default="bottom")
    subtitle_color: Literal["yellow", "white", "cyan"] = Field(default="yellow")


class DetailedScript(BaseModel):
    title: str = Field(
        description=(
            "YouTube Shorts用タイトル。全角22〜32文字程度。"
            "【損失回避・警告・暴露・数字】のフックを先頭に置き、末尾に必ず『 #Shorts』を付けること。"
            "例: '【知らないと全損】定価が存在しないネット社会の裏ルール #Shorts', '【警告】9割が搾取されている旅行予約の罠 #Shorts'"
        )
    )
    scenes: List[Scene] = Field(min_length=4, max_length=5, description="4〜5カットの構成")


# --- プロンプト構築（自己改善型＋タイトル強化） ---
def build_prompt(theme: str, angle: str, top_vids: List[Dict], worst_vids: List[Dict]) -> str:
    base_instructions = ""
    if os.path.exists(SYSTEM_PROMPT_FILE):
        try:
            with open(SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as f:
                base_instructions = f.read().strip()
        except Exception:
            pass

    if not base_instructions:
        base_instructions = """# 役割
あなたはYouTube Shortsでミリオン再生と最高視聴維持率を叩き出す凄腕の映像ディレクター兼コピーライターです。
知的好奇心ではなく「人間の恐怖心・損失回避・承認欲求・金銭欲」を直接刺激し、視聴者がスワイプの手を止める台本とタイトルを作成してください。

# タイトル命名ルール（最重要・厳格遵守）
1. 構造: 【強烈なフック単語】＋【具体的な自分ごと化ワード（数字・行動）】＋【 #Shorts】
2. 文字数: 全角22〜32文字以内（スマホ画面のShortsフィードで改行されても最も目立つ黄金比）。
3. 先頭フック候補:
   - 【知らないと損】 / 【※警告】 / 【閲覧注意】 / 【9割が損してる】 / 【プロが隠す闇】 / 【カモ確定】
4. NGタイトル（絶対禁止）:
   - 「〜について解説」「〜の仕組み」「〜の紹介」といった退屈な説明口調。
5. 必須: 末尾に必ず「 #Shorts」をスペース付きで付与すること。

# 構成ルール
1. 冒頭0.5秒のフック: 挨拶や前置きは厳禁。「実は〜」「まだ〜してる？」など、視聴者の無知や損失を突きつけること。
2. テンポ: 短文で言い切り、視聴者に考える隙を与えずに結論を連続投下する。
3. ループ誘導: 最終シーンの末尾を冒頭のセリフに自然に繋がる文脈にして、視聴維持率100%超えを狙う。
4. アクション喚起: 最終シーン末尾に「今すぐ保存して見返せ」「高評価と登録を」と短く指示する。"""

    learning_context = ""
    if top_vids and top_vids[0].get("views") is not None:
        learning_context = f"""
# 過去のデータに基づくアルゴリズム評価
【高再生・高維持率だった勝ちパターン】
{json.dumps(top_vids, ensure_ascii=False, indent=2)}

【伸び悩んだ負けパターン】
{json.dumps(worst_vids, ensure_ascii=False, indent=2)}
※ 勝ちパターンの言い回しやタイトルの煽り方を強く踏襲してください。
"""

    return f"""{base_instructions}
{learning_context}

# 今回の生成条件
【狙うテーマ】: {theme}
【必須アングル】: {angle}
"""


# --- Gemini API 呼び出し ---
def generate_with_gemini(prompt: str, max_retries: int = 3) -> DetailedScript:
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))
    gemini_models = ["gemini-3.8-flash", "gemini-3.7-flash"]

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
                    "temperature": 0.85,
                    "seed": random.randint(1, 10000000),
                },
            )
            if response.parsed:
                script = response.parsed
            else:
                script = DetailedScript.model_validate_json(response.text)

            # タイトル末尾に #Shorts が抜けていた場合の安全ガード
            if "#Shorts" not in script.title:
                script.title = f"{script.title.strip()} #Shorts"

            return script
        except Exception as e:
            last_error = e
            print(f"Gemini({model_name}) 試行 {attempt + 1}/{max_retries} 失敗: {e}")
            if attempt < max_retries - 1:
                time.sleep(3 * (attempt + 1))

    raise RuntimeError(f"台本生成に失敗しました: {last_error}")


def generate_script() -> DetailedScript:
    top_vids, worst_vids = load_history_with_metrics()

    theme = random.choice(PROFIT_THEMES)
    angle = random.choice(PROFIT_ANGLES)

    print(f"🎯 選定テーマ: {theme}")
    print(f"🔥 適用アングル: {angle}")

    prompt = build_prompt(theme, angle, top_vids, worst_vids)
    script = generate_with_gemini(prompt)

    save_initial_record(theme, angle, script.title)
    return script


if __name__ == "__main__":
    script = generate_script()
    print("\n=== 生成された台本 ===")
    print(script.model_dump_json(indent=2))
