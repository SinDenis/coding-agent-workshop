"""Step 03: describe a tool. Print the request, but do not execute it."""

import argparse
import json
import os
import readline  # noqa: F401 - enables Unicode-aware terminal editing for input()
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
MODEL = "deepseek/deepseek-v4-flash-0731"
SYSTEM = "Ты помощник программиста. Отвечай кратко по-русски."
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "shell",
            "description": "Выполнить команду в рабочей папке проекта.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
                "additionalProperties": False,
            },
        },
    }
]


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
            "tools": TOOLS,
            "provider": {"require_parameters": True},
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]


def show_response(response):
    print(json.dumps(response, ensure_ascii=False, indent=2))


def chat():
    messages = []
    while True:
        try:
            question = input("Ты> ").strip()
            question.encode("utf-8")  # Reject damaged input before adding it to history.
        except (EOFError, KeyboardInterrupt):
            return
        except UnicodeError:
            print('error: "Некорректный текст UTF-8; сообщение не отправлено"')
            print('help: "Повторите ввод сообщения"')
            continue
        if question == "/quit":
            return
        if not question:
            continue
        messages.append({"role": "user", "content": question})
        response = ask_model(messages)
        messages.append(response)
        show_response(response)
        if response.get("tool_calls"):
            print("Вызов показан, но исполнитель ещё не написан. Перезапустите для нового запроса.")
            return


def main():
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", nargs="?")
    args = parser.parse_args()
    if args.prompt is None:
        chat()
        return
    response = ask_model([{"role": "user", "content": args.prompt}])
    show_response(response)


if __name__ == "__main__":
    main()
