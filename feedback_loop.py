import json
import os
import googleapiclient.discovery
from google import genai

HISTORY_FILE = "history.json"
SYSTEM_PROMPT_FILE = "system_prompt.txt"
CHANNEL_ID = os.environ.get("YOUTUBE_CHANNEL_ID", "")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


def sync_metrics_and_optimize():
    """YouTubeの最新実績を取得してhistory.jsonを更新し、プロンプトを自己改善"""
    if not os.path.exists(HISTORY_FILE):
        print("history.json が存在しません。")
        return

    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        records = json.load(f)

    youtube = googleapiclient.discovery.build(
        "youtube", "v3", developerKey=YOUTUBE_API_KEY
    )

    # チャンネルの直近アップロード動画を取得
    res = youtube.channels().list(id=CHANNEL_ID, part="contentDetails").execute()
    uploads_id = res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    playlist_items = (
        youtube.playlistItems()
        .list(playlistId=uploads_id, part="snippet", maxResults=20)
        .execute()
    )

    video_map = {}
    for item in playlist_items.get("items", []):
        v_title = item["snippet"]["title"]
        v_id = item["snippet"]["resourceId"]["videoId"]
        video_map[v_title] = v_id

    if not video_map:
        print("取得可能な動画がありません。")
        return

    # 各動画の再生数・いいね数を取得
    v_stats_res = (
        youtube.videos()
        .list(id=",".join(video_map.values()), part="statistics")
        .execute()
    )
    stats_dict = {}
    for item in v_stats_res.get("items", []):
        stats_dict[item["id"]] = item.get("statistics", {})

    # history.json の実績データを更新
    updated = False
    for r in records:
        title = r.get("title")
        if title in video_map:
            v_id = video_map[title]
            stats = stats_dict.get(v_id, {})
            r["views"] = int(stats.get("viewCount", 0))
            r["likes"] = int(stats.get("likeCount", 0))
            r["comments"] = int(stats.get("commentCount", 0))
            # 簡易エンゲージメント率を維持率の近似指標として代入
            views = max(r["views"], 1)
            r["retention"] = round(
                (r["likes"] * 10 + r["comments"] * 20) / views, 4
            )
            updated = True

    if updated:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        print("📊 history.json の動画実績を最新化しました。")

    # 実績十分ならプロンプトをメタ改善
    valid_records = [r for r in records if r.get("views") is not None]
    if len(valid_records) >= 4:
        valid_records.sort(key=lambda x: x.get("views", 0), reverse=True)
        top = valid_records[:2]
        worst = valid_records[-2:]

        client = genai.Client(api_key=GEMINI_API_KEY)
        meta_prompt = f"""あなたはYouTube Shortsの収益最大化アルゴリズム責任者です。
以下の成績上位動画と下位動画を比較分析し、視聴維持率と再生数をさらに引き上げるための「system_prompt.txt」の全文を作成してください。

【勝ちパターン（高再生）】
{json.dumps(top, ensure_ascii=False, indent=2)}

【負けパターン（低再生）】
{json.dumps(worst, ensure_ascii=False, indent=2)}

※ 挨拶や解説は出力せず、そのまま保存できるプロンプト指示の文章のみを出力してください。
"""
        response = client.models.generate_content(
            model="gemini-3.8-flash", contents=meta_prompt
        )
        if response.text:
            cleaned_prompt = response.text.strip().removeprefix("```").removesuffix("```")
            with open(SYSTEM_PROMPT_FILE, "w", encoding="utf-8") as f:
                f.write(cleaned_prompt)
            print("🚀 system_prompt.txt を最新の実績に基づき自動アップデートしました。")


if __name__ == "__main__":
    sync_metrics_and_optimize()
