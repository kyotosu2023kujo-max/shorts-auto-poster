import os
import re
from google import genai
from google.genai import types

def generate_grounded_review_txt():
    api_key = os.environ.get("GEMINI_API_KEY")
    tracking_id = os.environ.get("AMAZON_TRACKING_ID", "yourtrackingid-22")

    if not api_key:
        raise ValueError("GEMINI_API_KEY が設定されていません。")

    client = genai.Client(api_key=api_key)

    grounding_tool = types.Tool(
        google_search=types.GoogleSearch()
    )

    system_instruction = f"""
あなたはnoteで高評価を得るプロのガジェット・トレンドレビュアーです。
必ずGoogle検索を用いて【現在日本国内で人気・話題のPC周辺機器・デスクアイテム・作業改善ガジェット】を1つ選定し、
実際のレビュー・口コミ・特徴をリサーチした上で記事を執筆してください。

【出力フォーマットの厳格なルール】
- 1行目: 記事タイトル（30〜45文字程度、読者を惹きつける実用的なもの。「タイトル:」などの接頭辞は付けずタイトル文字列のみを出力）
- 2行目: 必ず空行
- 3行目以降: 記事本文（見出し##、導入、スペック解説、使って感じたメリット3点、注意点・デメリット2点、おすすめできる人・できない人、まとめ）

【リンク埋め込みルール】
- 本文のまとめ直前に、選定した商品のAmazon検索URL（https://www.amazon.co.jp/s?k=商品名&tag={tracking_id}）を独立した行で1行配置してください。
"""

    prompt = "現在日本で人気・売れ筋の作業効率化ガジェットやデスク環境改善アイテムを1つリサーチし、指定フォーマットで記事を出力してください。"

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

    article_text = response.text.strip()

    # Markdownの余分なコードブロック記法があれば除去
    article_text = re.sub(r"^```(?:markdown|text)?\n", "", article_text)
    article_text = re.sub(r"\n```$", "", article_text)

    output_path = "article_output.txt"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(article_text)

    print(f"記事を {output_path} に保存しました。")

if __name__ == "__main__":
    generate_grounded_review_txt()
