import json
import os
import random
import urllib.parse
from collections import defaultdict
from typing import Dict, List, Literal, Optional
from google import genai
from pydantic import BaseModel, Field

# --- 定数・パス設定 ---
HISTORY_FILE = "history.json"
SYSTEM_PROMPT_FILE = "system_prompt.txt"
BOOK_OUTPUT_FILE = "reference_book.txt"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
AMAZON_TRACKING_ID = os.environ.get("AMAZON_TRACKING_ID", "yourtrackingid-22")

# --- 探索設定 ---
EXPLORE_RATIO = 0.7          # 探索の比率（活用は残り）
MIN_SAMPLES_TO_LEARN = 5     # この本数たまるまでフィードバックを使わない
RECENT_N_FOR_AVOID = 3       # 直近何本と型の組み合わせを被らせないか

# --- 変数1: ジャンル（既存THEMESはそのまま使用可。ここでは構造のみ示す） ---
THEMES = [
    # 既存の100テーマをそのまま残し、恐怖系以外も追加する
    "相対性理論のパラドックス", "光速の限界", "真空崩壊",
    # ...（既存テーマ）...
    # --- 追加: 恐怖系以外 ---
    "言葉の由来の意外な変遷", "動物の不思議な生態", "食べ物の科学",
    "日常のなぜ（信号・ボタン・色）", "数学・確率の直感に反する話",
    "世界の珍しい地理・風習", "仕事・人間関係の心理", "お金の仕組みの意外な事実",
    "睡眠と体内時計", "記憶と学習のコツ",
]

# --- 変数2: アングル（恐怖偏重を是正。感情トーン別に分類） ---
ANGLES_BY_TONE: Dict[str, List[str]] = {
    "恐怖・警告": ["禁忌の暴露", "致命的リスク", "監視の恐怖", "最悪のシミュレーション"],
    "驚き・種明かし": ["常識の否定", "日常からの抽象化", "構造の合致", "生化学的トリック", "物理的解析"],
    "ユーモア・軽さ": ["無用の効用", "不条理のゲーム理論", "理想と実態の乖離", "予想外の回答"],
    "感動・余韻": ["危機からの生還", "戦時下の異例の交歓", "最期のメッセージ", "探求者の異変"],
    "思考実験・挑発": ["倫理のジレンマ", "直感と確率の相違", "自己同一性のパラドックス", "思考実験の視覚化"],
    "実用・学び": ["体験設計の秘密", "合理的な最適解", "心理的報酬", "構造のハッキング"],
}

# --- 変数3〜7: 型の軸 ---
STYLE_AXES: Dict[str, List[str]] = {
    "語り口": ["淡々としたドキュメンタリー", "友人に話す口調", "インタビュー形式",
              "軽いツッコミ", "詩的", "ニュース速報風", "先生が教える口調"],
    "構成": ["結論先出し", "問いかけ始まり", "カウントダウン", "ifストーリー",
            "反転オチ", "3つの事実", "Q&A", "比較対決"],
    "視点": ["個人の体験", "視聴者本人", "第三者の観察", "モノや動物の視点", "数字の視点"],
    "結末": ["ループ", "オチ（笑い・驚き）", "問いを残す", "行動提案", "余韻"],
    "長さ": ["20秒", "30秒", "45秒"],
}

LENGTH_TO_CHARS = {"20秒": "100〜120字", "30秒": "150〜180字", "45秒": "230〜270字"}
LENGTH_TO_SCENES = {"20秒": "3シーン", "30秒": "4シーン", "45秒": "5シーン"}


class ReferenceBook(BaseModel):
    book_title: str = Field(description="動画テーマをさらに深く知るための実在する名著・学術書・新書・ノンフィクション。確実に実在するもののみ。")
    hook_comment: str = Field(description="固定コメント用の一言。視聴者が答えたくなる問いかけでもよい")


class Scene(BaseModel):
    narration: str = Field(description="ナレーションの読み上げ原稿")
    visual_search_queries: List[str] = Field(description="Pexels/Pixabay検索用の英語キーワードリスト")
    camera_motion: Literal["zoom_in", "zoom_out", "static"] = Field(description="カメラワーク演出")
    subtitle_text: str = Field(description="画面に表示するテロップ（14文字以内）")
    subtitle_color: Literal["yellow", "white", "cyan"] = Field(description="テロップのフォントカラー")
    subtitle_position: Literal["bottom", "center", "top"] = Field(description="テロップの画面配置位置")
    screen_effect: Optional[Literal["flash", "none"]] = Field(default="none", description="シーン切替時の画面効果")


class DetailedScript(BaseModel):
    title: str = Field(description="動画タイトル（#Shorts を含める）")
    theme: str = Field(description="選定されたテーマ")
    angle: str = Field(description="選定された構成アングル")
    opening_line: str = Field(description="冒頭の一文（第1シーンのナレーション冒頭と一致させる）")
    scenes: List[Scene] = Field(description="指定された長さに応じたシーン構成")
    reference_book: ReferenceBook = Field(description="実在書籍データ")
    uncertain_facts: List[str] = Field(default_factory=list, description="確信が持てない事実があれば列挙。なければ空")


# ------------------------------------------------------------
# 履歴管理
# ------------------------------------------------------------
def load_history() -> List[dict]:
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_history_record(script: DetailedScript, style: Dict[str, str], tone: str, mode: str):
    records = load_history()
    records.append({
        "title": script.title,
        "theme": script.theme,
        "angle": script.angle,
        "tone": tone,
        "opening_line": script.opening_line,
        "style": style,           # 語り口・構成・視点・結末・長さ
        "mode": mode,             # explore / exploit
        "views": None,            # 以下は投稿後に人間またはAPIで記入
        "likes": None,
        "comments": None,
        "retention": None,
        "swipe_rate": None,
        "avg_view_duration": None,
    })
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


# ------------------------------------------------------------
# 型の選定（直近と被らない組み合わせ）
# ------------------------------------------------------------
def pick_style(history: List[dict]) -> Dict[str, str]:
    recent_styles = [r.get("style") for r in history[-RECENT_N_FOR_AVOID:] if r.get("style")]
    recent_narration = [s.get("語り口") for s in history[-3:] if s.get("style")] if False else \
                       [r["style"].get("語り口") for r in history[-3:] if r.get("style")]

    for _ in range(50):
        style = {axis: random.choice(options) for axis, options in STYLE_AXES.items()}
        # 直近3本と同一の組み合わせは禁止
        if style in recent_styles:
            continue
        # 同じ語り口を3本連続で使わない
        if len(recent_narration) == 3 and all(n == style["語り口"] for n in recent_narration):
            continue
        return style
    return style


def pick_theme_and_angle(history: List[dict]):
    recent_themes = {r.get("theme") for r in history[-15:]}
    recent_tones = [r.get("tone") for r in history[-3:]]

    candidates = [t for t in THEMES if t not in recent_themes] or THEMES
    theme = random.choice(candidates)

    # 同じ感情トーンを3本連続で使わない
    tones = [t for t in ANGLES_BY_TONE if not (len(recent_tones) == 3 and all(x == t for x in recent_tones))]
    tone = random.choice(tones)
    angle = random.choice(ANGLES_BY_TONE[tone])
    return theme, tone, angle


# ------------------------------------------------------------
# フィードバック（条件を満たした場合のみ有効）
# ------------------------------------------------------------
def analyze_feedback(history: List[dict]) -> Dict[str, List[str]]:
    """
    軸ごとの選択肢について、MIN_SAMPLES_TO_LEARN本以上の実績があり、
    全体平均を上回るものだけを「採用候補」として返す。
    指標は retention（視聴維持率）を使用。データが足りなければ空を返す。
    """
    scored = [r for r in history if r.get("retention") is not None and r.get("style")]
    if len(scored) < MIN_SAMPLES_TO_LEARN * 2:
        return {}

    overall = sum(r["retention"] for r in scored) / len(scored)
    adopted: Dict[str, List[str]] = {}

    for axis in STYLE_AXES:
        bucket = defaultdict(list)
        for r in scored:
            bucket[r["style"].get(axis)].append(r["retention"])
        for option, values in bucket.items():
            if len(values) >= MIN_SAMPLES_TO_LEARN and (sum(values) / len(values)) > overall:
                adopted.setdefault(axis, []).append(option)
    return adopted


def decide_mode(adopted: Dict[str, List[str]]) -> str:
    if not adopted:
        return "explore"
    return "explore" if random.random() < EXPLORE_RATIO else "exploit"


def apply_exploit(style: Dict[str, str], adopted: Dict[str, List[str]]) -> Dict[str, str]:
    """活用モード: 採用済みの要素を一部の軸にだけ反映（全軸は固定しない）"""
    axes = random.sample(list(adopted.keys()), k=min(2, len(adopted)))
    for axis in axes:
        style[axis] = random.choice(adopted[axis])
    return style


# ------------------------------------------------------------
# 書籍リンク
# ------------------------------------------------------------
def save_reference_book(ref: ReferenceBook):
    encoded_query = urllib.parse.quote(ref.book_title)
    url = f"https://www.amazon.co.jp/s?k={encoded_query}&tag={AMAZON_TRACKING_ID}"
    content = (
        f"【参考文献】\n"
        f"📖 『{ref.book_title}』\n"
        f"{ref.hook_comment}\n"
        f"👉 {url}"
    )
    with open(BOOK_OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"📚 参考文献リンクを '{BOOK_OUTPUT_FILE}' に保存しました。")


# ------------------------------------------------------------
# プロンプト（探索モード既定）
# ------------------------------------------------------------
DEFAULT_PROMPT = """あなたはYouTube Shortsの制作ディレクターです。
目的は「当たる型を断定すること」ではなく、毎回ちがう型で試し、何が効くかを検証できる台本を作ることです。
過去の成功例を法則として固定してはいけません。指定された型（語り口・構成・視点・結末・長さ）に忠実に作ってください。

【共通ルール】
- 冒頭の1文でテーマの核心（驚き・結論・違和感・疑問）を提示する。挨拶や前置きは入れない。
- 1文は短く、聞いて意味が取れる文にする。
- 恐怖や戦慄を煽るのは、指定のトーンが恐怖系の場合のみ。それ以外では無理に怖くしない。
- テロップ（subtitle_text）は14文字以内。
- 数字・固有名詞・年代は確かなものだけ使う。不確かな点は断定せず「とされる」「説がある」と書く。
- 脚色した個人のストーリーは、再現やたとえ話だと分かる表現にする。
- 確信が持てない事実は uncertain_facts に列挙する。
- reference_book は確実に実在する書籍のみ。確信がなければ、定番の入門書・新書を選ぶ。"""


def get_base_system_prompt() -> str:
    """system_prompt.txt があれば優先（ただし自動上書きは行わず、人間が編集する運用を推奨）"""
    if os.path.exists(SYSTEM_PROMPT_FILE):
        try:
            with open(SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return content
        except Exception:
            pass
    return DEFAULT_PROMPT


def build_prompt(theme: str, tone: str, angle: str, style: Dict[str, str],
                 recent: List[dict]) -> str:
    forbidden_titles = "\n".join(f"- {r['title']}" for r in recent[-15:] if r.get("title")) or "なし"
    forbidden_openings = "\n".join(f"- {r['opening_line']}" for r in recent[-10:] if r.get("opening_line")) or "なし"
    length = style["長さ"]

    return f"""
{get_base_system_prompt()}

【今回の指定】
■ 題材ジャンル: {theme}
  （このジャンルの中から、「知っているつもりで知らない」具体的な話を自分で1つ選ぶこと）
■ 感情トーン: {tone}
■ アングル: {angle}
■ 語り口: {style['語り口']}
■ 構成: {style['構成']}
■ 視点: {style['視点']}
■ 結末: {style['結末']}
■ 長さ: {length}（ナレーション合計 {LENGTH_TO_CHARS[length]}、{LENGTH_TO_SCENES[length]}構成）

【重複禁止（直近のタイトル）】
{forbidden_titles}

【重複禁止（直近の冒頭の一文。似た書き出しも禁止）】
{forbidden_openings}

【出力要件】
- title: 35文字以内、末尾に #Shorts。定型タグ（【暴露】【警告】など）は使用禁止。
- opening_line: 第1シーンのナレーション冒頭の一文と一致させる。
- scenes: 指定の長さと構成に合わせる。
- 指定された語り口・構成・視点・結末を、全シーンで一貫して守ること。
"""


# ------------------------------------------------------------
# 生成
# ------------------------------------------------------------
def generate_with_gemini(prompt: str) -> DetailedScript:
    client = genai.Client(api_key=GEMINI_API_KEY)
    # モデル名は実在するものに置き換えてください（要確認）
    models_to_try = ["gemini-3.8-flash", "gemini-3.7-flash"]
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": DetailedScript,
                    "seed": random.randint(1, 10000000),
                },
            )
            return response.parsed
        except Exception as e:
            print(f"⚠️ {model_name} での生成失敗: {e}。次を試行します...")
    raise RuntimeError("利用可能な全Geminiモデルで台本生成に失敗しました。")


def generate_script() -> DetailedScript:
    history = load_history()

    theme, tone, angle = pick_theme_and_angle(history)
    style = pick_style(history)

    adopted = analyze_feedback(history)
    mode = decide_mode(adopted)
    if mode == "exploit":
        style = apply_exploit(style, adopted)

    print("🎲 選定結果:")
    print(f"   モード: {mode}")
    print(f"   ジャンル: {theme} / トーン: {tone} / アングル: {angle}")
    print(f"   型: {style}")
    if adopted:
        print(f"   採用済みの要素: {adopted}")
    else:
        print(f"   （フィードバック未反映: 実績が{MIN_SAMPLES_TO_LEARN * 2}本未満）")

    prompt = build_prompt(theme, tone, angle, style, history)
    script = generate_with_gemini(prompt)

    print(f"\n✅ 台本生成完了: {script.title}")
    if script.uncertain_facts:
        print(f"⚠️ 要確認の事実: {script.uncertain_facts}")

    save_history_record(script, style, tone, mode)
    save_reference_book(script.reference_book)
    return script


if __name__ == "__main__":
    generated = generate_script()
    print("\n--- 生成プレビュー ---")
    print(json.dumps(generated.model_dump(), ensure_ascii=False, indent=2))
