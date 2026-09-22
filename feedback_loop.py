import os
import json
import googleapiclient.discovery
from google import genai

# --- 設定 ---
SYSTEM_PROMPT_FILE = "system_prompt.txt"
HISTORY_FILE = "history.json"
CHANNEL_ID = os.environ.get("YOUTUBE_CHANNEL_ID", "")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


def get_video_metrics():
    """直近の動画から再生数・高評価数などのパフォーマンスを取得"""
    youtube = googleapiclient.discovery.build(
        "youtube", "v3", developerKey=YOUTUBE_API_KEY
    )

    # チャンネルのアップロード動画リストを取得
    res = (
        youtube.channels()
        .list(id=CHANNEL_ID, part="contentDetails")
        .execute()
    )
    uploads_playlist_id = res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    playlist_items = (
        youtube.playlistItems()
        .list(playlistId=uploads_playlist_id, part="snippet", maxResults=15)
        .execute()
    )

    video_ids = [
        item["snippet"]["resourceId"]["videoId"]
        for item in playlist_items.get("items", [])
    ]
    if not video_ids:
        return []

    # 動画の詳細データ（再生数、高評価数）を取得
    video_res = (
        youtube.videos()
        .list(id=",".join(video_ids), part="snippet,statistics")
        .execute()
    )

    performance_list = []
    for item in video_res.get("items", []):
        stats = item.get("statistics", {})
        snippet = item.get("snippet", {})
        performance_list.append(
            {
                "title": snippet.get("title", ""),
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
            }
        )

    # 再生数順にソート
    performance_list.sort(key=lambda x: x["views"], reverse=True)
    return performance_list


def optimize_prompt_with_gemini(performance_list):
    """上位と下位の動画を比較し、プロンプトを自動更新する"""
    if len(performance_list) < 4:
        print("💡 分析に必要な動画データ数が足りません（最低4本以上推奨）。")
        return

    top_videos = performance_list[:2]
    worst_videos = performance_list[-2:]

    with open(SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as f:
        current_prompt = f.read()

    meta_prompt = f"""# 依頼
あなたはYouTube Shortsのアルゴリズム最適化アナリストです。
以下に「直近で伸びた動画」と「伸び悩んだ動画」のデータ、および現在使用しているプロンプト（指示書）を提供します。

【高再生・高エンゲージメント動画（勝ちパターン）】
{json.dumps(top_videos, ensure_ascii=False, indent=2)}

【低再生・低エンゲージメント動画（負けパターン）】
{json.dumps(worst_videos, ensure_ascii=False, indent=2)}

【現在のプロンプト (system_prompt.txt)】
{current_prompt}

# 指示
1. 勝ちパターンのタイトル構成・フック・題材の共通項を抽出してください。
2. 負けパターンに見られる視聴離脱の原因（抽象的、冗長、既視感など）を特定してください。
3. その分析結果を踏まえ、次回以降の動画がよりバズりやすくなるよう、改善された【新しい system_prompt.txt の全文】を出力してください。
※余計な挨拶や解説は出力せず、ファイルにそのまま書き込めるプロンプト全文のみを出力してください。
"""

    client = genai.Client(api_key=GEMINI_API_KEY)
    gemini_models = ["gemini-3.8-flash", "gemini-3.7-flash"]

    new_prompt = None
    for model_name in gemini_models:
        try:
            res = client.models.generate_content(
                model=model_name,
                contents=meta_prompt,
            )
            if res.text:
                new_prompt = res.text.strip()
                # マークダウンのコードブロック記法が入っていたら除去
                if new_prompt.startswith("```"):
                    lines = new_prompt.split("\n")
                    new_prompt = "\n".join(lines[1:-1])
                break
        except Exception as e:
            print(f"⚠️ {model_name} での分析実行エラー: {e}")

    if new_prompt:
        with open(SYSTEM_PROMPT_FILE, "w", encoding="utf-8") as f:
            f.write(new_prompt)
        print("🚀 system_prompt.txt の自動改善・更新が完了しました。")
    else:
        print("❌ プロンプトの更新に失敗しました。")


if __name__ == "__main__":
    metrics = get_video_metrics()
    optimize_prompt_with_gemini(metrics)
