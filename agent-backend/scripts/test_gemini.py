import json
import urllib.error
import urllib.request

from utils.config import get_gemini_api_key, get_gemini_model


def main() -> None:
    model = get_gemini_model()
    key = get_gemini_api_key()
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={key}"
    )
    body = json.dumps(
        {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": 'Return JSON: {"ok": true, "message": "gemini-works"}'}],
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
            },
        }
    ).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        print("model:", model)
        print("reply:", text)
    except urllib.error.HTTPError as error:
        print("HTTP", error.code, error.read().decode()[:500])


if __name__ == "__main__":
    main()
