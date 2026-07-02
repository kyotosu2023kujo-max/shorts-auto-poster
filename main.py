import os
import json
from google import genai
from openai import OpenAI
from pydantic import BaseModel

# 台本のデータ構造
class Script(BaseModel):
    title: str
    narration: str
    visual_prompt: str

gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
groq_client = OpenAI(
    api_key=os.environ["GROQ_API_KEY"],
    base_url="https://api.groq.com/openai/v1"
)

PROMPT = "YouTube Shorts用の面白い雑学台本を書いて。JSON形式で出力して。"

def generate_with_gemini(prompt: str) -> Script | None:
    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": Script,
            },
        )
        return Script.model_validate_json(response.text)
    except Exception as e:
        print(f"Gemini失敗: {e}")
        return None

def generate_with_groq(prompt: str) -> Script | None:
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "必ずJSON形式のみで出力してください。title, narration, visual_promptの3キーを含めること。"},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content)
        return Script(**data)
    except Exception as e:
        print(f"Groq失敗: {e}")
        return None

def generate_script(prompt: str) -> Script:
    # 1. まずGeminiを試す
    result = generate_with_gemini(prompt)
    if result:
        return result

    # 2. ダメならGroqにフォールバック
    print("Groqにフォールバックします...")
    result = generate_with_groq(prompt)
    if result:
        return result

    raise RuntimeError("GeminiもGroqも失敗しました。")


script = generate_script(PROMPT)
print(script.model_dump_json(indent=2))
