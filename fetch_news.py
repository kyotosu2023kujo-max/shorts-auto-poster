import json
import random
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Dict

# スクレイピング遮断防止用ヘッダー
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}


def fetch_from_reddit_tips() -> Dict[str, str]:
    """Redditの生活裏ワザ・搾取回避系スレッド (r/LifeProTips) の週間Topから取得"""
    try:
        url = "https://www.reddit.com/r/LifeProTips/top.json?t=week&limit=25"
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            posts = data.get("data", {}).get("children", [])

        if not posts:
            raise ValueError("No posts found")

        # ランダムに1件選択
        post = random.choice(posts)["data"]
        raw_title = post.get("title", "")
        clean_title = re.sub(r"^LPT:?\s*", "", raw_title, flags=re.I)
        selftext = post.get("selftext", "")

        return {
            "source": "Reddit（r/LifeProTips）",
            "headline": clean_title,
            "context": (selftext[:350] if selftext else clean_title),
        }
    except Exception as e:
        print(f"⚠️ Reddit (LPT) 取得失敗: {e}")
        return {}


def fetch_from_reddit_psychology() -> Dict[str, str]:
    """Redditの心理学・人間関係の闇スレッド (r/psychology / r/todayilearned) から取得"""
    try:
        url = "https://www.reddit.com/r/todayilearned/search.json?q=psychology%20OR%20money%20OR%20scam&sort=top&t=month&limit=25"
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            posts = data.get("data", {}).get("children", [])

        if not posts:
            raise ValueError("No posts found")

        post = random.choice(posts)["data"]
        raw_title = post.get("title", "")
        clean_title = re.sub(r"^TIL(\s*that)?:?\s*", "", raw_title, flags=re.I)

        return {
            "source": "Reddit（心理・詐欺・経済トリビア）",
            "headline": clean_title,
            "context": f"海外で話題の心理・経済の裏事情: {clean_title}",
        }
    except Exception as e:
        print(f"⚠️ Reddit (TIL) 取得失敗: {e}")
        return {}


def fetch_from_consumer_rss() -> Dict[str, str]:
    """海外の経済・消費者トレンドニュース（CNBC / FTC系RSS）から取得"""
    try:
        # 消費者の罠や詐欺、マネートレンド系フィード
        feed_url = "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664"
        req = urllib.request.Request(feed_url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()

        root = ET.fromstring(xml_data)
        items = root.findall(".//item")
        if not items:
            raise ValueError("No RSS items found")

        item = random.choice(items[:15])
        title = item.find("title").text or ""
        desc = item.find("description").text or ""
        clean_desc = re.sub(r"<[^>]+>", "", desc)

        return {
            "source": "CNBC（金融・消費者トラブル・経済裏事情）",
            "headline": title,
            "context": clean_desc[:400],
        }
    except Exception as e:
        print(f"⚠️ 経済RSS取得失敗: {e}")
        return {}


def get_external_topic() -> Dict[str, str]:
    """3つのソースからランダムに1つ選択して高エンゲージメントなネタを取得"""
    fetchers = [
        fetch_from_reddit_tips,
        fetch_from_reddit_psychology,
        fetch_from_consumer_rss,
    ]
    random.shuffle(fetchers)

    for fetcher in fetchers:
        result = fetcher()
        if result and result.get("headline"):
            return result

    # 全滅時のバックアップ（損得・心理系の鉄板テーマ）
    fallbacks = [
        {
            "source": "Static Backup",
            "headline": "ダイナミックプライシングとCookieによる価格操作の罠",
            "context": "閲覧回数や端末のIPアドレスによって航空券やホテル、ECサイトの価格が秘密裏に吊り上げられる仕組み。",
        },
        {
            "source": "Static Backup",
            "headline": "返報性の原理を悪用した無料試食と無料体験のカラクリ",
            "context": "タダで何かを与えられると断れなくなる人間の脳のバグを利用した合法的な搾取手法。",
        },
    ]
    return random.choice(fallbacks)


if __name__ == "__main__":
    topic = get_external_topic()
    print("=== 取得した外部ネタ ===")
    print(f"取得元: {topic['source']}")
    print(f"タイトル/見出し: {topic['headline']}")
    print(f"概要: {topic['context']}")
