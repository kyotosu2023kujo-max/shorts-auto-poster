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
    6: "生活改善・デスクワークQOL向上アイテム（タンブラー、姿勢改善グッズなど）"
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
    本文中のAmazon URLを検出し、きれいな /dp/ASIN?tag=xxx 形式に正規化する。
    """
    # https://www.amazon.co.jp/.../dp/XXXXXXXXXX または /gp/product/XXXXXXXXXX のパターンを抽出
    asin_pattern = r"https?://(?:www\.)?amazon\.co\.jp/(?:[^/\s]+/)?(?:dp|gp/product)/([A-Z0-9]{10})"
    match = re.search(asin_pattern, text)
    
    if match:
        asin = match.group(1)
        clean_url = f"https://www.amazon.co.jp/dp/{asin}?tag={tracking_id}"
        # 既存のURL記述をクリーンなURLに置き換え
        # 行全体を単一のURLにする（前後に空行を確保）
        text = re.sub(r"https?://\S+amazon\.co\.jp\S+", clean_url, text)
        print(f"特定された商品ASIN: {asin} -> リンクを {clean_url} に整形しました。")
    else:
        print("【注意】個別のASINが見つからなかったため、URLの整形をスキップまたはフォールバックします。")
        
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
2. 検索キーワード一覧URL（/s?k=...）は絶対に禁止です。必ず特定の商品1つに直結する10桁のASIN（例: B0から始まる英数字）を含む「個別詳細ページURL」を見つけてください。
3. 特定したURLの末尾に、必ず指定のトラッキングタグを付与してください（例: https://www.amazon.co.jp/dp/B0XXXXXXXX?tag={tracking_id}）。
4. 記事末尾の「まとめ」の直前、または購入誘導箇所に、このアフィリエイトリンクを【独立した行】で配置してください（noteでブログカード展開させるため、前後に空行を入れて単独で置くこと）。

【出力フォーマット（厳格）】
- 1行目: 記事タイトル（30〜45文字程度、具体的な商品名とメリットを含める。「タイトル:」等の接頭辞は不要）
- 2行目: 必ず空行
- 3行目以降: 記事本文（見出し##、選定理由、良かった点3点、気になる点2点、おすすめな人・そうでない人、まとめ）
"""

    prompt = f"""
テーマ「{theme}」に基づき、過去に紹介した【{history_str}】以外から1つ実在する商品を選定してください。
Google検索で商品の詳細な特徴と、Amazon.co.jpの個別商品ページ（/dp/ASINコード）のURLを調べ、指定フォーマットでレビュー記事を作成してください。
"""

    print(f"本日のテーマ: {theme}")
    print(f"除外対象: {history_str}")
    print("Google検索で商品と個別Amazon URLをリサーチ中...")

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
    article_text = re.sub(r"^```(?:markdown|text)?\n", "", article_text)
    article_text = re.sub(r"\n```$", "", article_text)

    # Python側でURLの整合性チェックと正規化
    article_text = ensure_amazon_dp_link(article_text, tracking_id)

    # 1行目から商品・タイトルを履歴に追加
    first_line = article_text.split("\n")[0]
    append_history(first_line[:20])

    output_path = "article_output.txt"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(article_text)

    print(f"記事を {output_path} に保存しました。")

if __name__ == "__main__":
    generate_grounded_review_txt()
