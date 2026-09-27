import os
import json
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# 以降のコード（class NoteArticle...）はそのまま
class NoteArticle(BaseModel):
    title: str = Field(description="note読者の興味を惹くキャッチーな記事タイトル（30〜45文字程度）")
    summary: str = Field(description="記事の要約・導入リード文（100〜150文字程度）")
    body: str = Field(description="note本文（見出し、メリット・デメリット、ターゲット分析、URLプレースホルダーを含むMarkdown形式）")

def generate_affiliate_article(item_name: str, target_audience: str, affiliate_url: str) -> NoteArticle:
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

    system_instruction = """
あなたはnoteで高エンゲージメントを獲得するプロのガジェット・商品レビュアーです。
読者に押し売り感を与えず、フラットかつ説得力のある文体（「〜です・ます調」、適度な体験感・本音感）で記事を執筆してください。

【記事構成ルール】
1. タイトル: 結論やターゲット層が直感的に伝わる実用的なタイトル。
2. 導入: 読者の悩みへの共感と、この商品を選んだ背景。
3. 特徴・概要: スペックの羅列ではなく「生活がどう変わるか」に焦点を当てる。
4. メリット（良かった点）: 具体的な使用シーンを交えて3〜4点。
5. デメリット（気になった点）: 公平性を担保するため、正直な懸念点や注意点を2〜3点明記。
6. おすすめできる人／おすすめできない人: 箇条書きで明確に分類。
7. まとめ・リンク: noteのカード展開を意識し、URLは独立行で配置する。

【禁止事項・注意点】
- 過剰な煽り文句（「絶対に買うべき！」「神商品」の連発）は避ける。
- アフィリエイトリンクは必ず指定された単一URLを独立した行に配置する。
"""

    prompt = f"""
以下の条件に基づいて、note向けのレビュー記事を作成してください。

- 対象商品: {item_name}
- 想定読者層: {target_audience}
- アフィリエイトURL: {affiliate_url}

※ 本文内の購入誘導セクション（まとめ直前など）に、アフィリエイトURLを独立行で自然に挿入してください。
"""

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=NoteArticle,
            temperature=0.7,
        )
    )

    article_data = json.loads(response.text)
    return NoteArticle(**article_data)

if __name__ == "__main__":
    sample_item = "ロジクール MX Anywhere 3S (ワイヤレス静音マウス)"
    sample_target = "在宅勤務とカフェ作業を両立したいリモートワーカー・エンジニア"
    tracking_id = os.environ.get("AMAZON_TRACKING_ID", "yourtrackingid-22")
    sample_url = f"https://www.amazon.co.jp/dp/B0C4M5XYZ?tag={tracking_id}"

    result = generate_affiliate_article(sample_item, sample_target, sample_url)

    with open("article_output.json", "w", encoding="utf-8") as f:
        f.write(result.model_dump_json(indent=2))
        
    print("記事生成完了: article_output.json に保存しました。")
