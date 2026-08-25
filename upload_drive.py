import os
import sys
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def upload_to_drive(video_path: str):
    # GitHub Secrets から認証情報を取得（YouTubeのClient ID/Secretを共用できます）
    creds = Credentials(
        None,
        refresh_token=os.environ["GOOGLE_DRIVE_REFRESH_TOKEN"],
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token"
    )
    
    service = build("drive", "v3", credentials=creds)

    # 保存したいGoogleドライブのフォルダID（共有設定したフォルダのURLの末尾など）
    # ※特定のフォルダに入れずマイドライブの直下でよければこのままでOKです
    folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "18gihr80Ng-PdeUqFlxLB9IjnS9ZYfxGz")

    file_metadata = {
        "name": os.path.basename(video_path)
    }
    if folder_id:
        file_metadata["parents"] = [folder_id]
    
    media = MediaFileUpload(video_path, mimetype="video/mp4")
    
    print("Googleドライブへアップロード中...")
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id"
    ).execute()
    
    print(f"ドライブへの保存が完了しました！ ファイルID: {file.get('id')}")

if __name__ == "__main__":
    upload_to_drive("output_shorts.mp4")
