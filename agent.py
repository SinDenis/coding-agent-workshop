"""Step 08: a prompt-only Plan Mode is a request, not an enforced boundary."""

import argparse
import json
import os
import readline  # noqa: F401 - enables Unicode-aware terminal editing for input()
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
MAX_OUTPUT = 12000
MODEL = "deepseek/deepseek-v4-flash-0731"
SYSTEM = """Ты кодинговый агент в учебном проекте. Отвечай по-русски.
Изучи файлы перед правками. Используй shell для работы с проектом.
Команды уже запускаются в папке проекта. Используй относительные пути, не угадывай cwd.
Не меняй исходные тесты, чтобы скрыть ошибку. После правок запусти тесты.
Не утверждай, что проверка прошла, если не запускал её. В конце сообщи результат.
Не читай секреты, не обращайся за пределы рабочей папки и не используй сеть.
Для временных файлов используй текущую папку, не /tmp. Не делай лишних проверок.
"""
PLAN_PROMPT = """Ты планируешь изменение учебного проекта. Отвечай по-русски.
Изучи проект, задай вопросы при неясности, затем предложи конкретный план.
План краткий: до 6 пунктов, без кода реализации. Используй path="." для корня проекта.
Не изменяй файлы и не запускай команды, меняющие состояние. Жди подтверждения человека.
"""
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


def ask_model(messages, mode="act"):
    """The entire model call is visible: URL, headers, JSON and response."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise ValueError("Заполните OPENROUTER_API_KEY в локальном .env")
    response = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": os.getenv("OPENROUTER_MODEL", MODEL),
            "messages": [
                {"role": "system", "content": PLAN_PROMPT if mode == "plan" else SYSTEM},
                *messages,
            ],
            "max_tokens": 4096,
            "reasoning": {"enabled": False},
            "tools": TOOLS,
            "provider": {"require_parameters": True},
        },
        timeout=60,
    )
    if response.is_error:
        raise RuntimeError(
            f"OpenRouter HTTP {response.status_code}. Проверьте ключ, баланс и модель."
        )
    try:
        choice = response.json()["choices"][0]
        message = choice["message"]
        reason = choice["finish_reason"]
        calls = message.get("tool_calls") or []
        if message.get("role") != "assistant":
            raise ValueError("Ожидалось сообщение assistant")
        if reason not in ("stop", "tool_calls"):
            raise RuntimeError(f"Ответ не завершён нормально: finish_reason={reason}")
        if reason == "tool_calls" and not calls:
            raise ValueError("Нет ожидаемых вызовов инструментов")
        if not calls and not (message.get("content") or "").strip():
            raise ValueError("Модель вернула пустой ответ")
        ids = [call["id"] for call in calls]
        if len(set(ids)) != len(ids) or any(not isinstance(i, str) or not i for i in ids):
            raise ValueError("Неверные идентификаторы вызовов")
        for call in calls:
            if call["type"] != "function" or not isinstance(call["function"], dict):
                raise ValueError("Неверный формат вызова")
        # Preserve reasoning_details and all assistant fields for the next request.
        return message
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise RuntimeError("Некорректный ответ OpenRouter; выполнение остановлено") from exc


def show_response(response):
    print(json.dumps(response, ensure_ascii=False, indent=2))


def run_shell(command, workspace, timeout=30):
    # This is NOT a sandbox. cwd is a starting directory, not an access boundary.
    environment = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL") if key in os.environ}
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(
            command,
            shell=True,
            cwd=workspace,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            env=environment,
            start_new_session=True,
        )
        timed_out = False
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:
            # Linux/macOS/WSL. No background session survives a tool invocation.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        result = {}
        for name, stream in (("stdout", stdout), ("stderr", stderr)):
            stream.seek(0)
            raw = stream.read(MAX_OUTPUT + 1)
            text = raw[:MAX_OUTPUT].decode("utf-8", errors="replace")
            result[name] = text + ("\n[output truncated]" if len(raw) > MAX_OUTPUT else "")
        result["exit_code"] = process.returncode
        if timed_out:
            result["error"] = f"Таймаут команды: {timeout} секунд"
        return result


def execute_tool(call, workspace):
    try:
        function = call["function"]
        if function["name"] != "shell":
            return {"error": "Неизвестный инструмент"}
        arguments = json.loads(function["arguments"])
        if not isinstance(arguments, dict) or set(arguments) != {"command"}:
            return {"error": "Ожидается объект только с полем command"}
        command = arguments["command"]
        if not isinstance(command, str) or not command.strip():
            return {"error": "command должен быть непустой строкой"}
        print(f"shell: {command}")
        result = run_shell(command, workspace)
        print(json.dumps(result, ensure_ascii=False))
        return result
    except (KeyError, ValueError, TypeError, OSError) as exc:
        return {"error": f"Инструмент не выполнен: {type(exc).__name__}"}


def tool_result(call, result):
    return {
        "role": "tool",
        "tool_call_id": call["id"],
        "content": json.dumps(result, ensure_ascii=False),
    }


def agent_loop(messages, workspace, max_steps=20, mode="act"):
    for step in range(1, max_steps + 1):
        if len(json.dumps(messages, ensure_ascii=False)) > 150000:
            raise RuntimeError("История слишком велика. Начните новый диалог.")
        print(f"step: {step}")
        response = ask_model(messages, mode)
        messages.append(response)
        calls = response.get("tool_calls") or []
        if not calls:
            print(response.get("content") or "(нет текста)")
            print("stop: final_answer (корректность проверяется отдельно)")
            return response
        for call in calls:
            result = execute_tool(call, workspace)
            messages.append(tool_result(call, result))
    raise RuntimeError("Достигнут лимит шагов. Это не успешное завершение задачи.")


def chat(workspace, mode="act"):
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
        try:
            agent_loop(messages, workspace, mode=mode)
        except (RuntimeError, httpx.HTTPError, KeyboardInterrupt) as exc:
            print(f"stop: interrupted_or_error ({type(exc).__name__}). История очищена.")
            messages.clear()


def main():
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", nargs="?")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--plan", action="store_true", help="Планирование (пока только промпт)")
    args = parser.parse_args()
    workspace = args.workspace.resolve(strict=True)
    if not workspace.is_dir() or workspace in (ROOT, Path.home(), Path("/")):
        parser.error("Укажите отдельную копию учебного проекта, созданную prepare_demo.py")
    if args.prompt is None:
        chat(workspace, mode="plan" if args.plan else "act")
        return
    agent_loop(
        [{"role": "user", "content": args.prompt}], workspace, mode="plan" if args.plan else "act"
    )


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, OSError, httpx.HTTPError) as exc:
        print(f"stop: error ({type(exc).__name__}): {exc}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("stop: cancelled")
        sys.exit(130)
