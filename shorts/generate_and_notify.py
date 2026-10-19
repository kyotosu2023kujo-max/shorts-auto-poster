import json
import os
import requests
from scenario import generate_script, BOOK_OUTPUT_FILE

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
PENDING_SCENARIO_FILE = "pending_scenario.json"

def format_discord_message(script_data: dict) -> str:
    """Discordで見やすく表示するためのテキスト整形"""
    scenes_text = ""
    for i, scene in enumerate(script_data.get("scenes", []), 1):
        scenes_text += (
            f"**【Scene {i}】** ({scene['camera_motion']})\n"
            f"🗣️ ナレーション: `{scene['narration']}`\n"
            f"📺 テロップ: **{scene['subtitle_text']}** (色: {scene['subtitle_color']})\n"
            f"🔍 検索ワード: `{', '.join(scene['visual_search_queries'])}`\n\n"
        )

    ref_book = script_data.get("reference_book", {})

    msg = (
        f"🚨 **【台本確認リクエスト】Shorts新フレーバー生成完了** 🚨\n"
        f"----------------------------------------\n"
        f"📌 **タイトル**: {script_data.get('title')}\n"
        f"🎯 **テーマ**: {script_data.get('theme')}\n"
        f"📐 **アングル**: {script_data.get('angle')}\n\n"
        f"{scenes_text}"
        f"----------------------------------------\n"
        f"📖 **紹介予定の書籍**: 『{ref_book.get('book_title')}』\n"
        f"💬 **固定コメント**: {ref_book.get('hook_comment')}\n"
        f"----------------------------------------\n"
        f"⚠️ **【人間の手による微修正ガイド】**\n"
        f"1. AI特有の語尾（〜と考えられる）を語り口調（〜なんだよね）に修正\n"
        f"2. 冒頭か結末に直感的な感情表現を1言足す\n\n"
        f"✅ **修正・承認方法**: `pending_scenario.json` を編集して承認実行、またはメッセージに 👍 を付与"
    )
    return msg


def send_to_discord(script_data: dict):
    if not DISCORD_WEBHOOK_URL:
        print("⚠️ DISCORD_WEBHOOK_URL が設定されていません。コンソール出力のみ行います。")
        return

    payload = {
        "content": format_discord_message(script_data),
        "username": "台本検品AIディレクター"
    }

    res = requests.post(DISCORD_WEBHOOK_URL, json=payload)
    if res.status_code in [200, 204]:
        print("📲 Discordへ確認リクエストを送信しました。")
    else:
        print(f"❌ Discord送信失敗: {res.status_code} - {res.text}")


def main():
    # 台本生成
    script = generate_script()
    script_dict = script.model_dump()

    # 保留中データとして保存
    with open(PENDING_SCENARIO_FILE, "w", encoding="utf-8") as f:
        json.dump(script_dict, f, ensure_ascii=False, indent=2)

    # Discord通知
    send_to_discord(script_dict)

if __name__ == "__main__":
    main()
