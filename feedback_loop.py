import json
import os
from datetime import datetime
from typing import Dict, List

from google import genai
import googleapiclient.discovery

HISTORY_FILE = "history.json"
SYSTEM_PROMPT_FILE = "system_prompt.txt"

# 環境変数から認証情報を取得
CHANNEL_ID = os.environ.get("YOUTUBE_CHANNEL_ID", "")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


def get_channel_recent_videos(youtube, channel_id: str, max_results: int = 30) -> Dict[str, str]:
    """チャンネルのアップロード動画一覧（タイトル -> videoId の辞書）を取得"""
    res = youtube.channels().list(id=channel_id, part="contentDetails").execute()
    items = res.get("items", [])
    if not items:
        print("⚠️ チャンネルが見つかりませんでした。")
        return {}

    uploads_playlist_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

    playlist_items = (
        youtube.playlistItems()
        .list(playlistId=uploads_playlist_id, part="snippet", maxResults=max_results)
        .execute()
    )

    video_map = {}
    for item in playlist_items.get("items", []):
        title = item["snippet"]["title"]
        video_id = item["snippet"]["resourceId"]["videoId"]
        video_map[title] = video_id

    return video_map


def fetch_video_statistics(youtube, video_ids: List[str]) -> Dict[str, Dict]:
    """動画ID一覧から再生数・いいね数・コメント数を一括取得"""
    if not video_ids:
        return {}

    stats_map = {}
    # APIの制約（1回最大50件）
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i : i + 50]
        res = youtube.videos().list(id=",".join(chunk), part="statistics").execute()
        for item in res.get("items", []):
            v_id = item["id"]
            stats = item.get("statistics", {})
            stats_map[v_id] = {
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
            }
    return stats_map


def update_history_with_metrics():
    """history.json と YouTubeの実績を同期"""
    if not os.path.exists(HISTORY_FILE):
        print(f"⚠️ {HISTORY_FILE} が見つかりません。")
        return

    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        records = json.load(f)

    if not records:
        print("履歴データが空です。")
        return

    youtube = googleapiclient.discovery.build(
        "youtube", "v3", developerKey=YOUTUBE_API_KEY
    )

    print("🔍 YouTubeから直近の投稿動画を取得中...")
    video_map = get_channel_recent_videos(youtube, CHANNEL_ID)
    if not video_map:
        return

    video_ids = list(video_map.values())
    stats_map = fetch_video_statistics(youtube, video_ids)

    updated_count = 0
    for r in records:
        title = r.get("title", "")
        # タイトルで完全一致または部分一致を判定
        matched_id = None
        for yt_title, v_id in video_map.items():
            if title in yt_title or yt_title in title:
                matched_id = v_id
                break

        if matched_id and matched_id in stats_map:
            st = stats_map[matched_id]
            r["views"] = st["views"]
            r["likes"] = st["likes"]
            r["comments"] = st["comments"]

            # エンゲージメント率による維持率の近似スコア (0.00〜1.00)
            views = max(st["views"], 1)
            engagement_score = round(
                min(1.0, (st["likes"] * 10 + st["comments"] * 25) / views), 4
            )
            r["retention"] = engagement_score
            updated_count += 1

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"✅ {updated_count}件の動画メトリクスを {HISTORY_FILE} に反映しました。")


def optimize_system_prompt():
    """蓄積された上位・下位動画のデータからプロンプトを自己進化させる"""
    if not os.path.exists(HISTORY_FILE):
        return

    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        records = json.load(f)

    # 実績値が存在する動画を抽出
    evaluated = [r for r in records if r.get("views") is not None and r.get("views") > 0]

    # データ数が5本未満の場合は初期学習のサンプル不足としてスキップ
    if len(evaluated) < 5:
        print(f"ℹ️ 分析に必要な動画データが不足しています（現在: {len(evaluated)}本 / 最低5本必要）。スキップします。")
        return

    # 再生数 × 維持率近似値 で総合評価スコアを算出してソート
    evaluated.sort(key=lambda x: x.get("views", 0) * (x.get("retention", 0.1) + 0.5), reverse=True)

    top_performers = evaluated[:3]
    worst_performers = evaluated[-3:]

    print("\n🧠 Gemini による勝ちパターン・負けパターンのメタ分析を開始...")
    client = genai.Client(api_key=GEMINI_API_KEY)

    meta_prompt = f"""あなたはYouTube Shortsのアルゴリズムをハックし、再生維持率・インプレッションを極大化するプロのプロンプトエンジニア兼映像ディレクターです。

以下の【高実績動画（勝ちパターン）】と【低迷動画（負けパターン）】のデータを比較分析してください。
タイトル、テーマ、アングル、フックの切り口を比較し、何が視聴者のスワイプを防ぎ、何が離脱を招いたかを明確に抽出してください。

【高実績動画（勝ちパターン）】
{json.dumps(top_performers, ensure_ascii=False, indent=2)}

【低迷動画（負けパターン）】
{json.dumps(worst_performers, ensure_ascii=False, indent=2)}

この分析結果に基づき、次回以降の台本生成スクリプト（scenario.py）に読み込ませる「system_prompt.txt」の全文を作成・更新してください。

# 出力要件
- 解説や前置き、コードブロック記号（```）は一切出力しないでください。
- そのままファイルに上書き保存できるプレーンテキストのみを出力してください。
- 勝ちパターンの共通項（語彙、恐怖心・損失回避の煽り方、リズム）を「最優先ルール」として盛り込み、低迷した要因を「絶対禁止事項」として具体的に定義してください。
"""

    try:
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=meta_prompt,
        )
        if response.text:
            cleaned_text = response.text.strip().removeprefix("```").removesuffix("```").strip()
            with open(SYSTEM_PROMPT_FILE, "w", encoding="utf-8") as f:
                f.write(cleaned_text)
            print(f"🚀 {SYSTEM_PROMPT_FILE} を最新の分析結果に基づいて自動更新しました！")
    except Exception as e:
        print(f"⚠️ プロンプト自己改善処理に失敗しました: {e}")


if __name__ == "__main__":
    update_history_with_metrics()
    optimize_system_prompt()
