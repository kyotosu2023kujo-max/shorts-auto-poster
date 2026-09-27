import os
import json
import re
from google import genai
from google.genai import types

def clean_json_text(text: str) -> str:
    """Markdownコードブロック等を取り除いてJSON文字列を抽出"""
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())
    return text

def generate_grounded_review_article() -> dict:
    api_key = os.environ.get("GEMINI_API_KEY")
    tracking_id = os.environ.get("AMAZON_TRACKING_ID", "yourtrackingid-22")

    if not api_key:
        raise ValueError("GEMINI_API_KEY が設定されていません。")

    client = genai.Client(api_key=api_key)

    # Google検索ツールの設定
    grounding_tool = types.Tool(
        google_search=types.GoogleSearch()
    )

    system_instruction = """
あなたはnoteで高評価を得るプロのガジェット・トレンドレビュアーです。
必ずGoogle検索を用いて【現在（直近）日本国内で人気・売れ筋・話題となっているPC周辺機器・デスクアイテム・生活改善ガジェット】を1つ選定し、
実際のレビュー・口コミ・特徴をリサーチした上で記事を執筆してください。

【執筆ルール】
1. タイトル: 読者が思わず読みたくなる具体的で実用的なタイトル（30〜45字）。
2. リード文: 導入・共感（100〜150字）。
3. 本文構成:
   - なぜ今このアイテムが注目されているのか
   - 基本スペックと独自機能の解説
   - 実際のユーザー評判に基づく【良かった点・メリット（3点）】
   - 見逃せない【注意点・デメリット（2点）】
   - おすすめできる人／おすすめできない人（箇条書き）
   - まとめ
4. アフィリエイトリンク配置:
   - 本文のまとめ直前に、Amazon検索URL（指定のフォーマット）を独立した行で配置してください。

【出力フォーマット】
必ず以下のキーを持つJSON形式のみを出力してください（余計な前置きやマークダウンタグは最小限にすること）：
{
  "selected_item": "選定した商品名",
  "title": "記事タイトル",
  "summary": "リード文",
  "body": "Markdown形式の本文（見出し##、箇条書き、Amazon URLを含む）"
}
"""

    prompt = f"""
Google検索を使って、現在日本で話題・人気の「作業効率化ガジェット」「デスク周りの売れ筋アイテム」「テレワーク・勉強便利グッズ」の中から1つ実在する商品を選定し、レビュー記事を作成してください。

※ 記事末尾の購入リンク用には、選定した商品のAmazon検索URL（例: https://www.amazon.co.jp/s?k=商品名&tag={tracking_id}）を独立行で挿入してください。
"""

    print("Google検索を活用して最新トレンド商品をリサーチ中...")
    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=[grounding_tool],
            temperature=0.7,
        )
    )

    # レスポンスからJSONを抽出
    cleaned_text = clean_json_text(response.text)
    article_data = json.loads(cleaned_text)

    # 検索に使われたクエリやソース情報の確認用ログ
    if response.candidates and response.candidates[0].grounding_metadata:
        metadata = response.candidates[0].grounding_metadata
        if metadata.web_search_queries:
            print(f"実行された検索クエリ: {metadata.web_search_queries}")

    return article_data

if __name__ == "__main__":
    result = generate_grounded_review_article()

    print("\n--- リサーチ＆選定された商品 ---")
    print(result.get("selected_item"))
    print("\n--- タイトル ---")
    print(result.get("title"))

    # note投稿スクリプト（note_uploader.py）へ受け渡すため保存
    with open("article_output.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("\n記事データを article_output.json に正常保存しました。")
