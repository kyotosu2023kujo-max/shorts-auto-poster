import os

print("システム稼働テスト成功！")
print("環境変数GEMINI_API_KEYは設定されていますか？: " + str("GEMINI_API_KEY" in os.environ))
