import os
import datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def upload_to_youtube(video_path: str):
    # ======== 追加 ========
    # title.txt から生成されたタイトルを読み込む（ファイルが無ければデフォルト値）
    title = "自動生成雑学ショート"
    if os.path.exists("title.txt"):
        with open("title.txt", "r", encoding="utf-8") as f:
            title = f.read().strip()
    # ======================

    # GitHub Secretsから認証情報を取得
    creds = Credentials(
        None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token"
    )
    
    youtube = build("youtube", "v3", credentials=creds)

    # 読み込んだタイトルを活用
    body = {
        "snippet": {
            "title": f"{title} #Shorts #雑学",
            "description": "AIが自動生成した雑学ショート動画です。\n#Shorts #雑学 #豆知識",
            "tags": ["Shorts", "雑学", "豆知識"],
            "categoryId": "27"  # 27 = 教育
        },
        "status": {
            "privacyStatus": "public",  # テスト時は "private" に変更してください
            "selfDeclaredMadeForKids": False
        }
    }

    print(f"YouTubeへアップロードを開始します... [タイトル: {title}]")
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(video_path, chunksize=-1, resumable=True)
    )
    
    response = request.execute()
    print(f"アップロード完了！ URL: https://youtu.be/{response['id']}")

if __name__ == "__main__":
    upload_to_youtube("output_shorts.mp4")
