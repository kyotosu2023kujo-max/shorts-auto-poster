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

    auth_json = os.environ.get("NOTE_AUTH_JSON")
    if not auth_json:
        raise ValueError("NOTE_AUTH_JSON が環境変数に設定されていません。")

    with open("auth_state.json", "w", encoding="utf-8") as f:
        f.write(auth_json)

    with sync_playwright() as p:
        # ヘッドレスブラウザ起動
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            storage_state="auth_state.json",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        print("1. 投稿エディタへアクセス中...")
        page.goto("https://note.com/notes/new")
        page.wait_for_load_state("domcontentloaded")
        time.sleep(5)

        # 現在のURLを出力
        current_url = page.url
        print(f"==========================================")
        print(f"現在開いているURL: {current_url}")
        print(f"ページのタイトル: {page.title()}")
        print(f"==========================================")

        if "login" in current_url:
            print("【警告】ログイン画面にリダイレクトされています。Cookieが無効です。")
            raise RuntimeError("ログイン状態が切れています。auth.jsonの再作成が必要です。")

        print("2. タイトルと本文を入力中...")
        # 複数のセレクタ候補でタイトルを探す
        title_element = page.locator('textarea[placeholder*="タイトル"], input[placeholder*="タイトル"], textarea').first
        title_element.wait_for(state="visible", timeout=15000)
        title_element.fill(title)

        # 本文入力
        body_element = page.locator('.ProseMirror, [contenteditable="true"]').first
        body_element.wait_for(state="visible", timeout=15000)
        body_element.click()
        page.keyboard.insert_text(body)
        time.sleep(2)

        print("3. 下書きを保存中...")
        draft_btn = page.locator('button:has-text("下書き保存")')
        if draft_btn.is_visible():
            draft_btn.click()
            time.sleep(4)
            print("下書き保存ボタンをクリックしました。")
        else:
            print("自動保存を確認しました。")

        browser.close()
        
        if os.path.exists("auth_state.json"):
            os.remove("auth_state.json")

        print("🎉 完了: noteの下書き保存が正常に終了しました！")

if __name__ == "__main__":
    upload_to_note_draft("article_output.json")
