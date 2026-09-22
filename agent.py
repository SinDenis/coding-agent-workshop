"""Step 01: one HTTP request, one model response. No agent loop yet."""

import argparse
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
MODEL = "deepseek/deepseek-v4-flash-0731"
SYSTEM = "Ты помощник программиста. Отвечай кратко по-русски."


def ask_model(messages):
    """The entire model call is visible: URL, headers, JSON and response."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise ValueError("Заполните OPENROUTER_API_KEY в локальном .env")
    response = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": os.getenv("OPENROUTER_MODEL", MODEL),
            "messages": [{"role": "system", "content": SYSTEM}, *messages],
            "max_tokens": 4096,
            "reasoning": {"enabled": False},
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]


def main():
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt")
    args = parser.parse_args()
    response = ask_model([{"role": "user", "content": args.prompt}])
    print(response.get("content") or "(нет текста)")


if __name__ == "__main__":
    main()
