import json
import os
import random
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List, Literal, Tuple

from google import genai
from pydantic import BaseModel, Field

# --- ローカル設定 ---
HISTORY_FILE = "history.json"
SYSTEM_PROMPT_FILE = "system_prompt.txt"

# マンネリ防止用アングル
PERSPECTIVE_ANGLES = [
    "学会や常識を覆した狂気の逆転劇・パラドックス",
    "分子・ナノレベルの精密すぎる残酷な物理・生化学トラップ",
    "人類の倫理観や直感を完全に粉砕するグロテスクな合理的システム",
    "教科書には絶対に載せられない、実験の失敗・副作用がもたらした怪現象",
    "一見すると弱点に見える性質が、実は極限の武器へと昇華された瞬間",
]

# 共通ヘッダー
HTTP_HEADERS = {"User-Agent": "ShortsResearchBot/1.0 (Mozilla/5.0)"}


def fetch_from_wikipedia_unusual() -> Dict[str, str]:
    """Wikipediaの『良質な記事』からマニアックな項目を抽出"""
    try:
        url = (
            "https://ja.wikipedia.org/w/api.php?"
            "action=query&format=json&list=categorymembers&"
            "cmtitle=Category:%E8%89%AF%E8%B3%AA%E3%81%AA%E8%A8%98%E4%BA%8B&"
            "cmlimit=50&formatversion=2"
        )
        req = urllib.request.Request(url, headers=HTTP_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            members = data.get("query", {}).get("categorymembers", [])

        if not members:
            raise ValueError("記事が見つかりませんでした")

        target = random.choice(members)
        title = target["title"]

        summary_url = (
            "https://ja.wikipedia.org/w/api.php?"
            f"action=query&format=json&prop=extracts&exintro=1&explaintext=1&"
            f"titles={urllib.parse.quote(title)}&formatversion=2"
        )
        req_sum = urllib.request.Request(summary_url, headers=HTTP_HEADERS)
        with urllib.request.urlopen(req_sum, timeout=10) as res:
            res_data = json.loads(res.read().decode("utf-8"))
            extract = res_data["query"]["pages"][0].get("extract", "")

        return {
            "source": "Wikipedia（良質な記事）",
            "headline": title,
            "context": extract[:400],
        }
    except Exception as e:
        print(f"⚠️ Wikipedia取得失敗: {e}")
        return {}


def fetch_from_reddit_til() -> Dict[str, str]:
    """Redditの r/todayilearned のTopから取得"""
    try:
        url = "https://www.reddit.com/r/todayilearned/top.json?t=week&limit=25"
        reddit_headers = {
            "User-Agent": "script:shorts_research_bot:v1.0 (by /u/reddit_user_research)"
        }
        req = urllib.request.Request(url, headers=reddit_headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            posts = data.get("data", {}).get("children", [])

        if not posts:
            raise ValueError("投稿が見つかりませんでした")

        post = random.choice(posts)["data"]
        raw_title = post.get("title", "")
        clean_title = re.sub(r"^TIL(\s*that)?:?\s*", "", raw_title, flags=re.I)

        return {
            "source": "Reddit（r/todayilearned）",
            "headline": clean_title,
            "context": f"Redditで話題の事実: {clean_title}",
        }
    except Exception as e:
        print(f"⚠️ Reddit取得失敗: {e}")
        return {}


def fetch_from_science_rss() -> Dict[str, str]:
    """科学ニュースポータル（Phys.org）の最新ニュースRSSから取得"""
    try:
        feeds = [
            "https://phys.org/rss-feed/biology-news/",
            "https://phys.org/rss-feed/physics-news/",
        ]
        feed_url = random.choice(feeds)
        req = urllib.request.Request(feed_url, headers=HTTP_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()

        root = ET.fromstring(xml_data)
        items = root.findall(".//item")
        if not items:
            raise ValueError("RSS項目が見つかりませんでした")

        item = random.choice(items[:15])
        title = item.find("title").text or ""
        desc = item.find("description").text or ""
        clean_desc = re.sub(r"<[^>]+>", "", desc)

        return {
            "source": "Phys.org（科学ニュース・論文）",
            "headline": title,
            "context": clean_desc[:400],
        }
    except Exception as e:
        print(f"⚠️ RSS取得失敗: {e}")
        return {}


def get_external_topic() -> Dict[str, str]:
    """外部ソースからランダムに1件ネタを取得（失敗時はフォールバック）"""
    fetchers = [
        fetch_from_wikipedia_unusual,
        fetch_from_reddit_til,
        fetch_from_science_rss,
    ]
    random.shuffle(fetchers)

    for fetcher in fetchers:
        result = fetcher()
        if result and result.get("headline"):
            return result

    return {
        "source": "Fallback",
        "headline": "生物界における極小の寄生システム",
        "context": "宿主の行動を分子レベルでハイジャックする未知の寄生メカニズム",
    }


# --- 履歴管理 ---
def load_history() -> Tuple[List[str], List[str]]:
    """history.json から過去のテーマとタイトル一覧を取得"""
    if not os.path.exists(HISTORY_FILE):
        return [], []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            records = json.load(f)
            past_themes = [r.get("theme", "") for r in records if r.get("theme")]
            past_titles = [f"【{r.get('theme')}】{r.get('title')}" for r in records if r.get("title")]
            return past_themes, past_titles
    except Exception as e:
        print(f"⚠️ 履歴読み込み失敗（スキップ）: {e}")
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
        "title": title,
    })

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"📝 '{HISTORY_FILE}' に保存しました。")


# --- データスキーマ定義（クオリティ演出対応版） ---
class Scene(BaseModel):
    narration: str = Field(description="このシーンの読み上げナレーション（冗長さを排した鋭い語り口調）")
    subtitle_text: str = Field(description="画面中央〜下に大きく表示する強調テロップ（10〜15文字程度）")
    visual_search_queries: List[str] = Field(
        min_length=2,
        max_length=3,
        description="Pexels検索用キーワード候補。第1候補がヒットしなかった場合の第2・第3候補まで英語2〜3単語で指定（例: ['macro cell division', 'microscope bacteria', 'laboratory flask']）",
    )
    camera_motion: Literal["zoom_in", "zoom_out", "static"] = Field(
        default="zoom_in", description="カメラワーク演出"
    )
    screen_effect: Literal["none", "flash"] = Field(
        default="none", description="シーン転換時の一瞬の視覚効果（強調時はflash）"
    )
    subtitle_position: Literal["top", "center", "bottom"] = Field(
        default="bottom", description="テロップ表示位置"
    )
    subtitle_color: Literal["yellow", "white", "cyan"] = Field(
        default="yellow", description="テロップ文字色"
    )


class DetailedScript(BaseModel):
    title: str = Field(description="動画全体のフックになるタイトル（全角15〜20文字以内）")
    scenes: List[Scene] = Field(min_length=4, max_length=5, description="4〜5つのテンポの良いシーン構成")


# --- プロンプト構築 ---
def build_prompt(topic_info: Dict[str, str], angle: str, past_titles: List[str]) -> str:
    recent_history = past_titles[-15:] if len(past_titles) > 15 else past_titles

    base_instructions = ""
    if os.path.exists(SYSTEM_PROMPT_FILE):
        try:
            with open(SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as f:
                base_instructions = f.read().strip()
        except Exception as e:
            print(f"⚠️ {SYSTEM_PROMPT_FILE} 読み込み失敗: {e}")

    if not base_instructions:
        base_instructions = """# 依頼内容
あなたはYouTube Shortsでミリオン再生を狙う科学系リサーチャー兼映像ディレクターです。
視聴者が冒頭1秒で指を止め、最後まで離脱しないハイクオリティな演出構成と台本を作成してください。
冷笑的かつセンセーショナルで、直感を裏切る語り口調を採用してください。

# 演出・クオリティ要件
1. シーン構成: 4〜5カット構成。第1シーンは冒頭で強烈な違和感や問いを突きつけ、最終シーン末尾で高評価とチャンネル登録を促す。
2. 素材選定（Pexels API連携）:
   - 各シーンの `visual_search_queries` には、実写映像が確実にヒットする英語2〜3単語の候補を優先度順に2〜3個指定してください。
   - 抽象的すぎる単語（'science', 'nature'）は避け、具体的な被写体・構図（'deep sea glowing squid', 'microscope cells dividing', 'laser laboratory reflection'）を指定すること。
3. カメラワーク・エフェクト:
   - 冒頭シーンや衝撃の事実を明かすシーンには `screen_effect: flash` や動的な `camera_motion` を適切に割り当て、単調なスライドショー化を絶対に防ぐこと。
4. タイトル: 全角15〜20文字以内。"""

    return f"""{base_instructions}

# 原材料ネタ（Webより自動取得）
【ソース】: {topic_info['source']}
【元トピック/見出し】: {topic_info['headline']}
【詳細概要】: {topic_info['context']}

# 今回必須の切り口
【{angle}】

# 過去に作成した動画タイトル一覧（重複厳禁）
{json.dumps(recent_history, ensure_ascii=False, indent=2)}
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


# --- エントリー関数 ---
def generate_script() -> DetailedScript:
    past_themes, past_titles = load_history()

    topic_info = get_external_topic()
    selected_angle = random.choice(PERSPECTIVE_ANGLES)

    print(f"🌐 取得ネタ [{topic_info['source']}]: {topic_info['headline']}")
    print(f"🔍 アングル: {selected_angle}")

    prompt = build_prompt(topic_info, selected_angle, past_titles)
    script = generate_with_gemini(prompt)

    save_record(topic_info["headline"][:30], script.title)
    return script


if __name__ == "__main__":
    script = generate_script()
    print("\n=== 生成された台本 ===")
    print(script.model_dump_json(indent=2))
