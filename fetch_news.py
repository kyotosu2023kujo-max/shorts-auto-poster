import json
import random
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Dict

# 共通ヘッダー（スクレイピング遮断防止）
HEADERS = {"User-Agent": "ShortsResearchBot/1.0 (Mozilla/5.0)"}


def fetch_from_wikipedia_unusual() -> Dict[str, str]:
    """Wikipediaの『珍項目』や『良質な記事』からマニアックな記事をランダム抽出"""
    try:
        # Wikipedia API で「良質な記事」カテゴリからランダムに数件取得
        url = (
            "https://ja.wikipedia.org/w/api.php?"
            "action=query&format=json&list=categorymembers&"
            "cmtitle=Category:%E8%89%AF%E8%B3%AA%E3%81%AA%E8%A8%98%E4%BA%8B&"
            "cmlimit=50&formatversion=2"
        )
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            members = data.get("query", {}).get("categorymembers", [])

        if not members:
            raise ValueError("No articles found")

        # ランダムに1件選択
        target = random.choice(members)
        title = target["title"]

        # 記事の冒頭（サマリー）を取得
        summary_url = (
            "https://ja.wikipedia.org/w/api.php?"
            f"action=query&format=json&prop=extracts&exintro=1&explaintext=1&"
            f"titles={urllib.parse.quote(title)}&formatversion=2"
        )
        req_sum = urllib.request.Request(summary_url, headers=HEADERS)
        with urllib.request.urlopen(req_sum, timeout=10) as res:
            res_data = json.loads(res.read().decode("utf-8"))
            extract = res_data["query"]["pages"][0].get("extract", "")

        return {
            "source": "Wikipedia（良質な記事）",
            "headline": title,
            "context": extract[:400],  # 冒頭400字程度
        }
    except Exception as e:
        print(f"⚠️ Wikipedia取得失敗: {e}")
        return {}


def fetch_from_reddit_til() -> Dict[str, str]:
    """Redditの r/todayilearned (海外の意外な雑学スレッド) のTopから取得"""
    try:
        url = "https://www.reddit.com/r/todayilearned/top.json?t=week&limit=25"
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            posts = data.get("data", {}).get("children", [])

        if not posts:
            raise ValueError("No posts found")

        post = random.choice(posts)["data"]
        raw_title = post.get("title", "")
        # "TIL that..." を除去して読みやすく成形
        clean_title = re.sub(r"^TIL(\s*that)?:?\s*", "", raw_title, flags=re.I)

        return {
            "source": "Reddit（r/todayilearned）",
            "headline": clean_title,
            "context": f"Redditで話題の事実: {clean_title}",
        }
    except Exception as e:
        print(f"⚠️ Reddit取得失敗: {e}")
        return {}


def fetch_from_science_rss() -> Dict[str, str]:
    """科学ニュースポータル（Phys.org）の最新ニュースRSSから取得"""
    try:
        # 生物・物理・ナノテク系のRSS
        feeds = [
            "https://phys.org/rss-feed/biology-news/",
            "https://phys.org/rss-feed/physics-news/",
        ]
        feed_url = random.choice(feeds)
        req = urllib.request.Request(feed_url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()

        root = ET.fromstring(xml_data)
        items = root.findall(".//item")
        if not items:
            raise ValueError("No RSS items found")

        item = random.choice(items[:15])  # 直近15件からランダム
        title = item.find("title").text or ""
        desc = item.find("description").text or ""

        # HTMLタグの除去
        clean_desc = re.sub(r"<[^>]+>", "", desc)

        return {
            "source": "Phys.org（最新論文・科学ニュース）",
            "headline": title,
            "context": clean_desc[:400],
        }
    except Exception as e:
        print(f"⚠️ RSS取得失敗: {e}")
        return {}


def get_external_topic() -> Dict[str, str]:
    """3つのソースからランダムに1つ選択してネタを取得するメイン関数"""
    fetchers = [
        fetch_from_wikipedia_unusual,
        fetch_from_reddit_til,
        fetch_from_science_rss,
    ]
    random.shuffle(fetchers)

    for fetcher in fetchers:
        result = fetcher()
        if result and result.get("headline"):
            return result

    # すべて失敗したときのバックアップ（静的テーマ）
    return {
        "source": "Fallback",
        "headline": "生物界における極小の寄生システム",
        "context": "宿主の行動を分子レベルでハイジャックする未知の寄生メカニズム",
    }


if __name__ == "__main__":
    topic = get_external_topic()
    print("=== 取得した外部ネタ ===")
    print(f"取得元: {topic['source']}")
    print(f"タイトル/見出し: {topic['headline']}")
    print(f"概要: {topic['context']}")
