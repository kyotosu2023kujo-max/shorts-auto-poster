import os
import json
import time
from playwright.sync_api import sync_playwright

def upload_to_note_draft(json_file_path: str):
    # 生成された記事データの読み込み
    if not os.path.exists(json_file_path):
        raise FileNotFoundError(f"記事ファイルが見つかりません: {json_file_path}")

    with open(json_file_path, "r", encoding="utf-8") as f:
        article = json.load(f)

    title = article.get("title", "")
    body = article.get("body", "")

    note_email = os.environ.get("NOTE_EMAIL")
    note_password = os.environ.get("NOTE_PASSWORD")

    if not note_email or not note_password:
        raise ValueError("NOTE_EMAIL または NOTE_PASSWORD が環境変数に設定されていません。")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # 実装初期の検証時はPCブラウザの一般的なUser-Agentを設定
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        print("1. noteログインページにアクセス中...")
        page.goto("https://note.com/login")
        page.wait_for_load_state("networkidle")

        # ログイン処理
        page.fill('input[name="login"]', note_email)
        page.fill('input[name="password"]', note_password)
        page.click('button:has-text("ログイン")')
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        print("2. 投稿エディタへ移動中...")
        page.goto("https://note.com/notes/new")
        page.wait_for_load_state("networkidle")
        time.sleep(3)

        print("3. タイトルと本文を入力中...")
        # タイトル入力
        title_selector = 'textarea[placeholder="記事タイトル"]'
        page.wait_for_selector(title_selector)
        page.fill(title_selector, title)

        # 本文入力（ProseMirrorエディタ領域）
        body_selector = '.ProseMirror'
        page.wait_for_selector(body_selector)
        page.click(body_selector)
        
        # 改行やカード展開を正しく反映させるためテキストをキー入力
        page.keyboard.insert_text(body)
        time.sleep(2)

        print("4. 下書きを保存中...")
        # noteは自動保存も走りますが、明示的に「下書き保存」ボタンをクリック
        draft_button = page.locator('button:has-text("下書き保存")')
        if draft_button.is_visible():
            draft_button.click()
            time.sleep(3)
            print("下書き保存ボタンをクリックしました。")
        else:
            print("自動保存完了を確認しました。")

        browser.close()
        print("完了: noteの下書き保存が正常に終了しました！")

if __name__ == "__main__":
    upload_to_note_draft("article_output.json")
