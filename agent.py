"""Step 04: the model requests, Python executes. No feedback to the model yet."""

import argparse
import json
import os
import readline  # noqa: F401 - enables Unicode-aware terminal editing for input()
import subprocess
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


def run_shell(command, workspace):
    # This is NOT a sandbox. cwd is a starting directory, not an access boundary.
    result = subprocess.run(
        command,
        shell=True,
        cwd=workspace,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=30,
        env={key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL") if key in os.environ},
    )
    return {"stdout": result.stdout, "stderr": result.stderr, "exit_code": result.returncode}


def execute_tool(call, workspace):
    function = call["function"]
    if function["name"] != "shell":
        return {"error": "Неизвестный инструмент"}
    arguments = json.loads(function["arguments"])
    print(f"shell: {arguments['command']}")
    result = run_shell(arguments["command"], workspace)
    print(json.dumps(result, ensure_ascii=False))
    return result


def run_turn(messages, workspace):
    response = ask_model(messages)
    messages.append(response)
    show_response(response)
    for call in response.get("tool_calls") or []:
        execute_tool(call, workspace)
    return response


def chat(workspace):
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
        response = run_turn(messages, workspace)
        if response.get("tool_calls"):
            print("Команда выполнена. Модель ещё не получила результат. Здесь останавливаемся.")
            return


def main():
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", nargs="?")
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    args = parser.parse_args()
    workspace = args.workspace.resolve(strict=True)
    if args.prompt is None:
        chat(workspace)
        return
    run_turn([{"role": "user", "content": args.prompt}], workspace)


if __name__ == "__main__":
    main()
