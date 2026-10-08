import os
import re
from datetime import datetime
from google import genai
from google.genai import types

# 曜日ごとのジャンル定義（月=0, 火=1, ..., 日=6）
THEMES = {
    0: "PC入力デバイス（マウス、トラックボール、エルゴノミクスキーボードなど）",
    1: "デスク配線・電源周り（急速充電器、CIO・Anker製品、ケーブルホルダーなど）",
    2: "デスク環境・疲労軽減（モニターアーム、デスクマット、リストレスト、アイケア）",
    3: "外出・カフェ作業向けポータブルアイテム（軽量PCスタンド、ガジェットポーチ、多機能ハブ）",
    4: "集中力向上・作業用オーディオ（ノイズキャンセリングイヤホン、骨伝導ヘッドセットなど）",
    5: "知的生産・自己投資（思考整理ノート、定番の教養・仕事術・効率化の書籍）",
    6: "生活改善・デスクワークQOL向上アイテム（タンブラー、姿勢改善グッズなど）",
}

HISTORY_FILE = "reviewed_items.txt"


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def append_history(item_name):
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"{item_name}\n")


def ensure_amazon_dp_link(text: str, tracking_id: str) -> str:
    """
    本文中のAmazon URLまたはASINを検出し、
    noteで確実にブログカード化できるよう独立行の /dp/ASIN?tag=xxx に整形する。
    """
    asin_pattern = r"(?:amazon\.co\.jp/(?:[^/\s]+/)?(?:dp|gp/product)/|ASIN[:：\s]*)([A-Z0-9]{10})"
    match = re.search(asin_pattern, text)

    if match:
        asin = match.group(1)
        clean_url = f"\n\nhttps://www.amazon.co.jp/dp/{asin}?tag={tracking_id}\n\n"

        # 既存のMarkdownリンク [テキスト](URL) や 生URL を、前後に空行のある独立URLに置換
        text = re.sub(
            r"\[.*?\]\(https?://\S*amazon\.co\.jp\S*\)|https?://\S*amazon\.co\.jp\S*",
            clean_url.strip(),
            text,
        )
        # 前後に確実に空行を確保して note でのカード展開を保証
        text = re.sub(
            rf"(\n*)https://www.amazon.co.jp/dp/{asin}\?tag={tracking_id}(\n*)",
            clean_url,
            text,
        )
        print(f"特定された商品ASIN: {asin} -> リンクを正規化しました。")
    else:
        print("【注意】個別のASINが見つかりませんでした。")

    return text


def generate_grounded_review_txt():
    api_key = os.environ.get("GEMINI_API_KEY")
    tracking_id = os.environ.get("AMAZON_TRACKING_ID", "yourtrackingid-22")

    if not api_key:
        raise ValueError("GEMINI_API_KEY が設定されていません。")

    # 本日のテーマ決定
    weekday = datetime.now().weekday()
    theme = THEMES.get(weekday, "デスク作業改善ガジェット")

    history = load_history()
    history_str = "、".join(history[-15:]) if history else "なし"

    client = genai.Client(api_key=api_key)
    grounding_tool = types.Tool(google_search=types.GoogleSearch())

    system_instruction = f"""
あなたはnoteで多くの支持を集めるレビュー・効率化ライターです。
必ずGoogle検索を用いて【現在日本国内で人気・売れ筋の定番〜注目のアイテム】を1つ選定し、
実際のレビュー・口コミ・特徴、およびAmazon.co.jpの【個別商品ページURL】をリサーチして記事を執筆してください。

【厳守：除外リスト】
以下の商品は過去に紹介済みのため、絶対に選ばないでください：
{history_str}

【本日の選定テーマ】
{theme}

【最重要：Amazon商品リンクの生成要件】
1. 選定した商品の「Amazon.co.jpの個別詳細ページURL」をGoogle検索を通じて特定してください。
   形式例: https://www.amazon.co.jp/dp/B0XXXXXXXX
2. 検索結果一覧URL（/s?k=...）は禁止です。必ず特定の商品1つに直結する10桁のASIN（例: B0から始まる英数字）を含む「個別詳細ページURL」を見つけてください。
3. 特定したURLの末尾にトラッキングタグを付与してください（例: https://www.amazon.co.jp/dp/B0XXXXXXXX?tag={tracking_id}）。
4. 記事末尾の「まとめ」の直前に、このアフィリエイトリンクを【前後に空行を入れた単独行】で配置してください（Markdownリンク [テキスト](URL) にせず、生URLを単独で置くこと）。

【出力フォーマット（厳格）】
- 1行目: 記事タイトル（30〜45文字程度、具体的な商品名とメリットを含める。「タイトル:」等の接頭辞は不要）
- 2行目: 必ず空行
- 3行目以降: 記事本文（見出し##、選定理由、良かった点3点、気になる点2点、おすすめな人・そうでない人、単独行のAmazon URL、まとめ）
"""

    prompt = f"""
テーマ「{theme}」に基づき、過去に紹介した【{history_str}】以外から1つ実在する商品を選定してください。
Google検索で商品の詳細な特徴と、Amazon.co.jpの個別商品ページ（/dp/ASINコード）のURLを調べ、指定フォーマットでレビュー記事を作成してください。
"""

    print(f"本日のテーマ: {theme}")
    print(f"除外対象: {history_str}")
    print("Google検索で商品と個別Amazon URLをリサーチ中...")

    # temperature 等の廃止予定パラメータを除去し、安全に呼び出し
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=[grounding_tool],
        ),
    )

    article_text = response.text.strip()
    article_text = re.sub(r"^```(?:markdown|text)?\n", "", article_text)
    article_text = re.sub(r"\n```$", "", article_text)

    # Python側でURLの整合性チェックと正規化
    article_text = ensure_amazon_dp_link(article_text, tracking_id)

    # 1行目のタイトルから商品特定用の文字を履歴に追加
    first_line = article_text.split("\n")[0].strip()
    append_history(first_line)

    output_path = "article_output.txt"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(article_text)

    print(f"記事を {output_path} に保存しました。")


if __name__ == "__main__":
    generate_grounded_review_txt()
