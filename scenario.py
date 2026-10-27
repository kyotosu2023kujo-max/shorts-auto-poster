import json
import os
import random
import urllib.parse
from typing import List, Literal, Optional
from google import genai
from pydantic import BaseModel, Field

# --- 定数・パス設定 ---
HISTORY_FILE = "history.json"
SYSTEM_PROMPT_FILE = "system_prompt.txt"
BOOK_OUTPUT_FILE = "reference_book.txt"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
AMAZON_TRACKING_ID = os.environ.get("AMAZON_TRACKING_ID", "yourtrackingid-22")

THEMES = [
    # 科学・宇宙・生体 (1-20)
    "相対性理論のパラドックス", "光速の限界", "真空崩壊",
    "量子もつれ", "地球磁場逆転", "深海超高圧",
    "人工知能の意識", "事象の地平面", "老化メカニズム",
    "脳細胞の物理的破壊", "突発的氷河期", "フェルミのパラドックス",
    "超伝導", "ウイルスの進化史", "太陽フレア",
    "グレイ・グー仮説", "記憶の上書き", "プラズマ閉じ込め",
    "ヒッグス場", "宇宙マイクロ波背景放射",

    # 歴史・事件・国家の闇 (21-40)
    "古代王国の突然の消滅", "マインドコントロール実験", "偽札による経済謀略",
    "エニグマ暗号の欺瞞", "中世ペストの狂気", "潜水艦沈没の隠蔽",
    "エルドラド探検隊の全滅", "世界恐慌の投機集団", "ローマ帝国の鉛中毒",
    "独裁者の食事検査法", "秘密核実験都市", "要塞陥落の盲点",
    "砂漠の人工建造物", "壊血病の人体実験", "核ミサイル発射拒否",
    "偽旗作戦の歴史", "不老不死薬の真実", "ロンドンの死の煙霧",
    "三十年戦争の狂乱", "地下バンカーの極秘物資",

    # 経済・金融・搾取構造 (41-60)
    "生体データの転売", "サブスクの心理工学", "インフレの資産格差",
    "ビットコインの正体", "カジノの空間設計", "保険金の不払い特約",
    "国家の借金と通貨発行", "高級ブランドの焼却", "高頻度取引の罠",
    "タックスヘイブン", "暗殺された発明家", "クレジットスコアの支配",
    "中古車市場のレモン市場", "ファストファッションの汚染", "製薬カルテルの価格操作",
    "名ばかり管理職", "ダイヤモンドの市場操作", "銀行の信用創造",
    "オーバーブッキングの確率", "競合の買い殺し防衛",

    # 心理・洗脳・人間関係 (61-80)
    "カルトのマインドコントロール", "サイコパスの進化論", "毒親の言葉の暴力",
    "ギャンブル依存症の報酬系", "ガスライティング", "アイヒマン実験の集団心理",
    "恋愛ドーパミンの賞味期限", "微表情と瞳孔の収縮", "SNSの同調圧力",
    "詐欺師の小さな貸し", "認知的不協和", "スタンフォード監獄実験",
    "慢性微小炎症と脳の変調", "ダークトライアドの心理", "尋問の沈黙テクニック",
    "バーナム効果", "返報性の原理の悪用", "カリギュラ効果",
    "ハロー効果の評価", "傍観者効果の麻痺",

    # 雑学・都市伝説・日常の裏側 (81-100)
    "スマホの液晶汚染", "飛行機トイレの凍結", "エレベーターの閉ボタン",
    "ボツリヌストキシンの美容利用", "防犯カメラの死角マップ", "自動販売機のルーレット制御",
    "足首だけの靴の怪異", "ホテル清掃員の禁忌備品", "無添加食品の抜け穴",
    "青信号の歴史的齟齬", "ギロチン刑囚の意識持続", "ポイント・ネモの人工衛星",
    "ランサムウェアの国家ハッカー", "100年腐らない完全食品", "コンビニのゴールデンライン",
    "無意識に飲み込む昆虫数", "エスカレーターの速度差", "高圧電線の鳥の耐性",
    "手術室のBGMのメリット", "植物の猛毒成分と誤食",
]
ANGLES = [
    # 警告・禁止・恐怖 (1-20)
    "禁忌の暴露", "致命的リスク", "恐怖による引き込み",
    "不都合な真実", "日常の罠", "常識の否定",
    "悲惨な末路", "監視の恐怖", "行動の強制",
    "ターゲットの限定", "冷徹な事実検証", "最悪のシミュレーション",
    "秘匿された裏側", "都市伝説の裏付け", "禁断の知識",
    "緊急の警鐘", "最期のメッセージ", "決定的瞬間の言語化",
    "カウントダウン", "検索禁忌の領域",

    # 逆張り・パラドックス・暴露 (21-40)
    "逆説の証明", "善行のパラドックス", "非公開の法則",
    "無用の効用", "統計の残酷さ", "未成文のルール",
    "不条理のゲーム理論", "有益の裏の害悪", "真のインセンティブ",
    "思考の陥穽", "非対称な搾取", "自由のパラドックス",
    "依存の病理", "裏の抑止力", "構造のハッキング",
    "通説の否定", "過剰適合の弊害", "真の価値の乖離",
    "機能不全のメカニズム", "理想と実態の乖離",

    # なぜ？・種明かし・論理展開 (41-60)
    "日常からの抽象化", "視線誘導の原理", "構造の合致",
    "空間心理学", "致命的な偶発性", "集合のメカニズム",
    "形態の工学的必然", "未解明の痕跡", "生化学的トリック",
    "誘導の必然性", "恐怖の消費心理", "臨界点のメカニズム",
    "再現不能の謎", "暗号の解読", "驚異の認知能力",
    "物理的解析", "体験設計の秘密", "構造的強靭さ",
    "環境圧による適応", "心理的報酬",

    # ストーリー・追体験・タイムリミット (61-80)
    "緊迫のタイムリミット", "極限の生存選択", "密室の心理劇",
    "転落の追体験", "暴走の引き金", "破局の時系列解析",
    "当事者の証言", "孤独下の生存確率", "危機からの生還",
    "独自の秩序の崩壊", "臨界点直前の心理", "日常の次元崩壊",
    "構造破壊の瞬間", "力学の巨視的検証", "異才の精神変容",
    "戦時下の異例の交歓", "限界状態の検証", "探求者の異変",
    "破滅的な環境変容", "システム崩壊の初期流出",

    # クイズ・思考実験・挑発 (81-100)
    "倫理のジレンマ", "直感と確率の相違", "違和感の凝視",
    "高難度の論理的挑戦", "トレードオフ", "本性の暴露テスト",
    "極限下の即決要求", "認知バイアスの露呈", "合理的な最適解",
    "自己同一性のパラドックス", "錯覚の知覚テスト", "主観的世界の検証",
    "意識の物理的解釈", "思考実験の視覚化", "時間悖論の罠",
    "予測アルゴリズムの提示", "予想外の回答", "忌避すべきシグナル",
    "環境変化の進化論", "仕掛けられたメッセージ",
]

class ReferenceBook(BaseModel):
    book_title: str = Field(description="動画テーマをさらに深く知るための実在する名著・学術書・新書・ノンフィクション（例: 『毒と薬の世界史』『利己的な遺伝子』など）")
    hook_comment: str = Field(description="固定コメント用の一言（例: 『この狂気的な実験と隠蔽工作の全記録を記した禁断の文献はこちら』）")


class Scene(BaseModel):
    narration: str = Field(description="ナレーションの読み上げ原稿（1.4倍速でテンポよく話す）")
    visual_search_queries: List[str] = Field(description="Pexels/Pixabay検索用の英語キーワードリスト（例: ['dark laboratory microscope', 'cellular motion']）")
    camera_motion: Literal["zoom_in", "zoom_out", "static"] = Field(description="カメラワーク演出")
    subtitle_text: str = Field(description="画面下部に大きく表示するテロップ（14文字以内の短文）")
    subtitle_color: Literal["yellow", "white", "cyan"] = Field(description="テロップのフォントカラー")
    subtitle_position: Literal["bottom", "center", "top"] = Field(description="テロップの画面配置位置")
    screen_effect: Optional[Literal["flash", "none"]] = Field(default="none", description="シーン切替時の画面効果")


class DetailedScript(BaseModel):
    title: str = Field(description="動画タイトル（#Shorts を含める）")
    theme: str = Field(description="選定されたテーマ")
    angle: str = Field(description="選定された構成アングル")
    scenes: List[Scene] = Field(description="4〜5シーンの構成リスト")
    reference_book: ReferenceBook = Field(description="世界観を補強する実在書籍データ")


def load_recent_history(n: int = 15) -> List[str]:
    """直近n件の投稿タイトルを取得（ネタの重複防止）"""
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            records = json.load(f)
            return [r.get("title", "") for r in records[-n:] if r.get("title")]
    except Exception:
        return []


def save_history_record(title: str, theme: str, angle: str):
    """生成したタイトルとマトリクス選定結果を history.json に保存"""
    records = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                records = json.load(f)
        except Exception:
            records = []

    records.append({
        "title": title,
        "theme": theme,
        "angle": angle,
        "views": None,
        "likes": None,
        "comments": None,
        "retention": None,
    })

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def save_reference_book(ref: ReferenceBook):
    """固定コメント・概要欄投稿用に書籍アソシエイトリンクを書き出し"""
    encoded_query = urllib.parse.quote(ref.book_title)
    amazon_search_url = f"https://www.amazon.co.jp/s?k={encoded_query}&tag={AMAZON_TRACKING_ID}"

    comment_content = (
        f"【本動画の参考文献・さらに深い真実を知る名著】\n"
        f"📖 『{ref.book_title}』\n"
        f"{ref.hook_comment}\n"
        f"👉 {amazon_search_url}"
    )

    with open(BOOK_OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(comment_content)
    print(f"📚 参考文献アソシエイトリンクを '{BOOK_OUTPUT_FILE}' に保存しました。")


def get_base_system_prompt() -> str:
    """自己改訂された system_prompt.txt が存在すればそれを優先読み込み"""
    if os.path.exists(SYSTEM_PROMPT_FILE):
        try:
            with open(SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return content
        except Exception:
            pass

    return """あなたはYouTube Shortsのアルゴリズムをハックし、視聴維持率とインプレッションを極大化するショート動画専任のトップディレクターです。
視聴者が日常で意識していない「脳のバグ・社会の裏ルール・歴史の暗部・生物の異常性・資本の罠」を突きつけ、スワイプの手を強制停止させる台本を作成してください。

【構成ルール】
1. 冒頭（第1シーン）: 最初の1秒で常識破壊・警告・恐怖を突きつけ、スワイプを反射的に止めさせる（screen_effectは'flash'を推奨）。
2. 展開（第2〜3シーン）: 矢継ぎ早に具体的な証拠、数字、心理トリックを畳み掛ける。退屈を感じる隙を1ミリも与えない。
3. 結末（最終シーン）: 視聴者に強い余韻、戦慄、またはコメント欄で議論したくなる問いかけを残す。冒頭へループできる構文を意識する。
4. 全体の長さ: 4〜5シーン構成。各シーンのナレーションはテンポよく読み上げて30〜45秒に収める。
5. テロップ（subtitle_text）: 1画面あたり8〜14文字以内。短く力強い単語で画面を支配する。
6. 参考文献（reference_book）: テーマの深層に実在する名著（学術書、新書、ノンフィクション）を1冊選定すること。"""


def generate_with_gemini(theme: str, angle: str, forbidden_titles: List[str]) -> DetailedScript:
    """Gemini 3.8 Flash を用いて動画台本JSONを生成（非推奨パラメータ完全排除）"""
    client = genai.Client(api_key=GEMINI_API_KEY)

    system_instruction = get_base_system_prompt()
    forbidden_text = "\n".join([f"- {t}" for t in forbidden_titles]) if forbidden_titles else "なし"

    prompt = f"""
{system_instruction}

【今回の指令】
以下の「テーマ」と「構成アングル」を有機的に融合させ、冷徹かつ知的好奇心を刺激するショート動画台本を生成せよ。

■ 抽象テーマ: {theme}
■ 構成アングル（フック手法）: {angle}

【重複禁止リスト（直近のタイトル）】
以下の過去タイトルとネタや切り口が被ることは絶対に許されない:
{forbidden_text}

【出力要件】
- title: 全角22〜32文字程度。知的好奇心・本能的恐怖を刺激する硬質な名詞を使い、末尾に #Shorts を付与せよ。安っぽい【暴露】【警告】などの定型タグは使用禁止。
- scenes: 4〜5つのシーン。各シーンにナレーション、Pexels/Pixabay検索キーワード（英語複数）、カメラワーク、テロップ情報を含めること。
- reference_book: その事象や歴史を学術的・体系的に追及した実在の書籍名と紹介文を含めること。
"""

    models_to_try = ["gemini-3.8-flash", "gemini-3.7-flash"]
    for model_name in models_to_try:
        try:
            # temperature, top_p, top_k などのサンプリングパラメータは廃止対応のため除外
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": DetailedScript,
                    "seed": random.randint(1, 10000000),
                },
            )
            return response.parsed
        except Exception as e:
            print(f"⚠️ {model_name} での生成失敗: {e}。次を試行します...")

    raise RuntimeError("利用可能な全Geminiモデルで台本生成に失敗しました。")


def generate_script() -> DetailedScript:
    """マトリクス選定・重複回避・生成・履歴保存を一貫して実行"""
    forbidden_titles = load_recent_history(n=15)

    selected_theme = random.choice(THEMES)
    selected_angle = random.choice(ANGLES)

    print(f"🎲 マトリクス選定完了:")
    print(f"   テーマ: {selected_theme}")
    print(f"   アングル: {selected_angle}")

    script = generate_with_gemini(selected_theme, selected_angle, forbidden_titles)

    print(f"\n✅ 台本生成完了: {script.title}")
    save_history_record(script.title, selected_theme, selected_angle)
    save_reference_book(script.reference_book)

    return script


if __name__ == "__main__":
    generated = generate_script()
    print("\n--- 生成プレビュー ---")
    print(json.dumps(generated.model_dump(), ensure_ascii=False, indent=2))
