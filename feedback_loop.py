import json
import os
import re
from typing import Dict, List, Tuple
from google import genai
from googleapiclient.discovery import build

HISTORY_FILE = "history.json"
SYSTEM_PROMPT_FILE = "system_prompt.txt"
CONFIG_FILE = "video_style_config.json"

DEFAULT_STYLE_CONFIG = {
    "voice_rate": "+38%",
    "voice_volume_boost": 1.5,
    "max_cut_duration": 3.0,
    "zoom_ratio": 0.15,
    "font_size": 68,
    "subtitle_y_offset": 680,
    "subtitle_bg_box": True,
    "subtitle_bg_opacity": 180,
    "spectrum_box_size": 340,
    "spectrum_icon_size": 135,
    "spectrum_y_offset": 450,
    "opening_flash_enabled": True,
    "default_subtitle_color": "yellow",
}


def get_youtube_client():
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        return None
    return build("youtube", "v3", developerKey=api_key)


def sync_youtube_metrics():
    """YouTube APIから直近の動画実績を取得し、history.json を更新"""
    channel_id = os.environ.get("YOUTUBE_CHANNEL_ID")
    youtube = get_youtube_client()

    if not youtube or not channel_id:
        print("⚠️ YOUTUBE_API_KEY または YOUTUBE_CHANNEL_ID が未設定のため実績同期をスキップ。")
        return

    if not os.path.exists(HISTORY_FILE):
        return

    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        records = json.load(f)

    # チャンネルの最新動画リストを取得
    try:
        res = youtube.search().list(
            part="snippet",
            channelId=channel_id,
            maxResults=30,
            order="date",
            type="video"
        ).execute()

        video_items = res.get("items", [])
        if not video_items:
            return

        video_ids = [item["id"]["videoId"] for item in video_items]
        stats_res = youtube.videos().list(
            part="snippet,statistics",
            id=",".join(video_ids)
        ).execute()

        yt_data_map = {}
        for item in stats_res.get("items", []):
            title = item["snippet"]["title"]
            stats = item["statistics"]
            views = int(stats.get("viewCount", 0))
            likes = int(stats.get("likeCount", 0))
            comments = int(stats.get("commentCount", 0))
            yt_data_map[title] = {
                "views": views,
                "likes": likes,
                "comments": comments,
                "retention": min(1.0, round((likes + comments * 2) / max(views, 1) * 10, 2))
            }

        # タイトル前方一致でマッピング更新
        for r in records:
            for yt_title, metrics in yt_data_map.items():
                if r["title"].split("#")[0].strip() in yt_title:
                    r.update(metrics)
                    break

        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        print("📊 YouTube実績の同期が完了しました。")

    except Exception as e:
        print(f"⚠️ YouTube API連携エラー: {e}")


def load_evaluated_records() -> Tuple[List[Dict], List[Dict]]:
    if not os.path.exists(HISTORY_FILE):
        return [], []
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        records = json.load(f)

    evaluated = [r for r in records if r.get("views") is not None]
    if len(evaluated) < 3:
        return [], []

    evaluated.sort(
        key=lambda x: (x.get("views", 0) * (x.get("retention", 0.5) + 0.5)),
        reverse=True
    )
    return evaluated[:3], evaluated[-3:]


def optimize_system_prompt(top_vids: List[Dict], worst_vids: List[Dict]):
    """台本用システムプロンプトの自己改訂"""
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))

    current_prompt = ""
    if os.path.exists(SYSTEM_PROMPT_FILE):
        with open(SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as f:
            current_prompt = f.read()

    meta_prompt = f"""
YouTube Shortsの分析担当として、以下の実績データをもとに台本生成用システムプロンプトを改訂してください。

【高評価動画群（勝ちパターン）】
{json.dumps(top_vids, ensure_ascii=False, indent=2)}

【低迷動画群（負けパターン）】
{json.dumps(worst_vids, ensure_ascii=False, indent=2)}

【現在のシステムプロンプト】
{current_prompt}

# 改訂要件
- 勝ちパターンのタイトル構造、フック、展開の共通点を抽出しルールに組み込む。
- 負けパターンの要素を禁止事項に明記する。
- 余計な解説は省き、完成した新しいプロンプト全文のみを出力せよ。
"""
    res = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=meta_prompt
    )
    new_prompt = res.text.strip()

    with open(SYSTEM_PROMPT_FILE, "w", encoding="utf-8") as f:
        f.write(new_prompt)
    print(f"🔄 '{SYSTEM_PROMPT_FILE}' を自動改訂しました。")


def optimize_style_config(top_vids: List[Dict], worst_vids: List[Dict]):
    """映像演出パラメータ (video_style_config.json) の自動チューニング"""
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))

    current_config = DEFAULT_STYLE_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                current_config.update(json.load(f))
        except Exception:
            pass

    config_prompt = f"""
YouTube Shortsの映像ディレクターとして、実績データを踏まえ演出設定JSONの各数値を微調整せよ。

【高評価動画】: {json.dumps(top_vids, ensure_ascii=False)}
【低迷動画】: {json.dumps(worst_vids, ensure_ascii=False)}
【現在の演出設定】: {json.dumps(current_config, ensure_ascii=False)}

# 調整ルール
- voice_rate: +30% 〜 +45%
- zoom_ratio: 0.10 〜 0.25
- font_size: 64 〜 74
- subtitle_bg_opacity: 140 〜 220
- default_subtitle_color: "yellow", "white", "cyan" のいずれか
- マークダウン等の装飾は一切つけず、純粋なJSONオブジェクトのみを出力せよ。
"""
    res = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=config_prompt
    )

    clean_json = re.sub(r"^```json\s*|\s*```$", "", res.text.strip(), flags=re.MULTILINE)
    try:
        new_config = json.loads(clean_json)
        merged_config = {**current_config, **new_config}
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(merged_config, f, ensure_ascii=False, indent=2)
        print(f"⚙️ '{CONFIG_FILE}' を最適化しました。")
    except Exception as e:
        print(f"⚠️ 演出設定の更新スキップ (JSON解析失敗): {e}")


def run_feedback_loop():
    sync_youtube_metrics()
    top_vids, worst_vids = load_evaluated_records()

    if not top_vids:
        print("ℹ️ 分析に必要な実績データが不足しています（最低3本必要）。")
        return

    print("🧠 Geminiによる自律改善ループを実行中...")
    optimize_system_prompt(top_vids, worst_vids)
    optimize_style_config(top_vids, worst_vids)


if __name__ == "__main__":
    run_feedback_loop()
