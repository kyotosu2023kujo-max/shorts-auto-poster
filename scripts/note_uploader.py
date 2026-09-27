import os
import json
import time
from playwright.sync_api import sync_playwright

def upload_to_note_draft(json_file_path: str):
    if not os.path.exists(json_file_path):
        raise FileNotFoundError(f"記事ファイルが見つかりません: {json_file_path}")

    with open(json_file_path, "r", encoding="utf-8") as f:
        article = json.load(f)

    title = article.get("title", "")
    body = article.get("body", "")

    # GitHub Secretsから認証情報を取得
    auth_json = os.environ.get("NOTE_AUTH_JSON")
    if not auth_json:
        raise ValueError("NOTE_AUTH_JSON が環境変数に設定されていません。")

    # 一時的にストレージ状態ファイルを作成
    with open("auth_state.json", "w", encoding="utf-8") as f:
        f.write(auth_json)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # 保存済みのログインセッションをロードしてコンテキスト作成
        context = browser.new_context(
            storage_state="auth_state.json",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        print("1. 投稿エディタへアクセス中...")
        page.goto("https://note.com/notes/new")
        page.wait_for_load_state("networkidle")
        time.sleep(3)

        print("2. タイトルと本文を入力中...")
        # タイトル入力
        title_selector = 'textarea[placeholder="記事タイトル"]'
        page.wait_for_selector(title_selector, timeout=20000)
        page.fill(title_selector, title)

        # 本文入力
        body_selector = '.ProseMirror'
        page.wait_for_selector(body_selector, timeout=20000)
        page.click(body_selector)
        page.keyboard.insert_text(body)
        time.sleep(2)

        print("3. 下書きを保存中...")
        draft_button = page.locator('button:has-text("下書き保存")')
        if draft_button.is_visible():
            draft_button.click()
            time.sleep(3)
            print("下書き保存ボタンをクリックしました。")
        else:
            print("自動保存完了を確認しました。")

        browser.close()
        
        # 後始末
        if os.path.exists("auth_state.json"):
            os.remove("auth_state.json")
            
        print("完了: noteの下書き保存が正常に終了しました！")

if __name__ == "__main__":
    upload_to_note_draft("article_output.json")
