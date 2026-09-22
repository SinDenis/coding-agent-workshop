"""Opt-in live checks. Run from the repo root; responses/costs stay in ignored .checks/."""

import argparse
import builtins
import hashlib
import inspect
import json
import os
import subprocess
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from prepare_demo import prepare  # noqa: E402


def load_agent(ref):
    source = subprocess.check_output(["git", "show", f"{ref}:agent.py"], cwd=ROOT, text=True)
    module = types.ModuleType("stage_agent")
    module.__file__ = str(ROOT / "agent.py")
    exec(compile(source, f"{ref}/agent.py", "exec"), module.__dict__)
    return module


def fingerprint(path):
    return {
        str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in path.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }


def assert_final_answer(calls):
    last = calls[-1]["choices"][0]
    assert last["finish_reason"] == "stop", "Agent did not finish normally"
    assert not last["message"].get("tool_calls"), "Agent still requested tools"
    assert last["message"].get("content"), "No final answer"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Required: allow paid API requests")
    parser.add_argument("--tag", default="HEAD")
    parser.add_argument("--scenario", choices=["smoke", "fix", "plan", "full"], default="smoke")
    args = parser.parse_args()
    if not args.live:
        parser.error("Добавьте --live, чтобы разрешить платные запросы")
    load_dotenv(ROOT / ".env")
    if not os.getenv("OPENROUTER_API_KEY"):
        parser.error("Нет OPENROUTER_API_KEY в .env")
    if not os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-v4-flash-0731").startswith("deepseek/"):
        parser.error("Эта репетиция бюджета рассчитана на выбранную модель DeepSeek")
    checks = ROOT / ".checks"
    checks.mkdir(exist_ok=True)
    ledger_path = checks / "live-budget.json"
    ledger = (
        json.loads(ledger_path.read_text())
        if ledger_path.exists()
        else {
            "reserved_usd": 0,
            "actual_usd": 0,
            "requests": [],
        }
    )
    original_post = httpx.post
    calls = []

    def measured_post(url, **kwargs):
        payload = kwargs["json"]
        # Apply an upper provider price before reserving a pessimistic per-request budget.
        payload.setdefault("provider", {}).update(
            {
                "max_price": {"prompt": 1, "completion": 2, "request": 0},
            }
        )
        estimate = (len(json.dumps(payload).encode()) + 16000) / 1_000_000
        estimate += payload["max_tokens"] * 2 / 1_000_000
        if ledger["reserved_usd"] + estimate > 4.9:
            raise RuntimeError("Предохранитель: суммарный резерв проверок близок к $5")
        ledger["reserved_usd"] += estimate
        ledger_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
        response = original_post(url, **kwargs)
        data = response.json()
        cost = (data.get("usage") or {}).get("cost")
        record = {
            "tag": args.tag,
            "scenario": args.scenario,
            "status": response.status_code,
            "cost_usd": cost,
            "time": datetime.now(timezone.utc).isoformat(),
        }
        if cost is not None:
            ledger["actual_usd"] += cost
        ledger["requests"].append(record)
        ledger_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
        calls.append(data)
        if response.is_error:
            print("API status:", response.status_code, flush=True)
        return response

    module = load_agent(args.tag)
    httpx.post = measured_post
    workspace = prepare()
    report = {
        "tag": args.tag,
        "scenario": args.scenario,
        "workspace": str(workspace),
        "model": os.getenv("OPENROUTER_MODEL", module.MODEL),
    }
    try:
        history = [
            {
                "role": "user",
                "content": (
                    "Выполни ровно одну команду shell: printf workshop-ok. "
                    "После результата ответь коротко и не вызывай инструменты снова."
                ),
            }
        ]
        has_mode = "mode" in inspect.signature(module.ask_model).parameters
        if args.scenario in ("fix", "full"):
            history[0]["content"] = (
                "Исправь ошибку done в tasks.py: завершается не та задача. "
                "Сначала прочитай проект и запусти python -m unittest discover -v. "
                "Не меняй test_tasks.py. После исправления запусти исходные тесты снова."
            )
            original_tests = (workspace / "test_tasks.py").read_bytes()
            module.agent_loop(history, workspace)
            assert (workspace / "test_tasks.py").read_bytes() == original_tests, "Tests changed"
            result = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-v"],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=20,
            )
            print(result.stderr, flush=True)
            assert result.returncode == 0, "Acceptance tests still fail"
            report["acceptance_passed"] = True
            if args.scenario == "full":
                before_plan = fingerprint(workspace)
                original_input = builtins.input
                lines = iter(
                    [
                        "/plan",
                        "Изучи проект и предложи план. Добавь необязательный флаг --store PATH: "
                        "с ним задачи сохраняются в JSON между запусками. "
                        "Без него поведение прежнее. "
                        "Если файла нет, начинаем с исходных задач. Повреждённый JSON: ненулевой "
                        "код выхода, понятная ошибка, файл не перезаписывать. "
                        "Пока ничего не меняй.",
                        "/approve",
                        "/quit",
                    ]
                )

                def user_input(prompt):
                    line = next(lines)
                    if line == "/approve":
                        assert fingerprint(workspace) == before_plan, "Plan modified files"
                        report["read_only_verified"] = True
                    print(prompt + line, flush=True)
                    return line

                builtins.input = user_input
                try:
                    module.chat(workspace)
                finally:
                    builtins.input = original_input
                assert_final_answer(calls)
                report["agent_turn_completed"] = True

                def cli(*arguments):
                    return subprocess.run(
                        [sys.executable, "tasks.py", *arguments],
                        cwd=workspace,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )

                result = cli("--store", "acceptance.json", "--command", "add Семинар")
                assert result.returncode == 0, result.stdout + result.stderr
                result = cli("--store", "acceptance.json", "--command", "list")
                assert result.returncode == 0 and "Семинар" in result.stdout
                assert (workspace / "acceptance.json").exists(), "No persisted file"
                (workspace / "corrupt.json").write_text("not-json", encoding="utf-8")
                result = cli("--store", "corrupt.json", "--command", "list")
                assert result.returncode != 0, "Corrupted data silently accepted"
                assert (workspace / "corrupt.json").read_text() == "not-json", "Data overwritten"
                assert (workspace / "test_tasks.py").read_bytes() == original_tests
                result = subprocess.run(
                    [sys.executable, "-m", "unittest", "discover", "-v"],
                    cwd=workspace,
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                assert result.returncode == 0, result.stderr
                report["approved_implementation_verified"] = True
        elif args.scenario == "plan":
            history[0]["content"] = (
                "Изучи проект доступными инструментами. Кратко предложи план сохранения задач "
                "между запусками в JSON-файле tasks.json в рабочей папке. "
                "При повреждённом JSON нужна понятная ошибка без перезаписи файла. "
                "Сейчас только план, ничего не выполняй."
            )
            before = fingerprint(workspace)
            module.agent_loop(history, workspace, mode="plan")
            assert fingerprint(workspace) == before, "Plan modified files"
            assert any(m["role"] == "tool" for m in history), "Plan did not inspect project"
            report["read_only_verified"] = True
        elif args.tag.startswith(("step-01", "step-02")):
            message = module.ask_model([{"role": "user", "content": "Ответь одним словом: привет"}])
            assert message.get("content"), "Empty answer"
            if args.tag.startswith("step-02"):
                message = module.ask_model(
                    [
                        {"role": "user", "content": "Ответь одним словом: привет"},
                        message,
                        {"role": "user", "content": "Какое слово ты только что написал?"},
                    ]
                )
                assert "привет" in message.get("content", "").lower()
        elif args.tag.startswith("step-03"):
            message = module.ask_model(history)
            assert message.get("tool_calls"), "No requested tool call"
        elif hasattr(module, "run_turn"):
            module.run_turn(history, workspace)
            tool_calls = [m for m in history if m.get("tool_calls")]
            assert tool_calls, "No tool call"
            if args.tag.startswith("step-05"):
                assert any(m["role"] == "tool" for m in history)
                assert len(calls) == 2, "Manual feedback needs two requests"
        else:
            module.agent_loop(history, workspace, **({"mode": "act"} if has_mode else {}))
            assert any(m["role"] == "tool" for m in history), "No tool was executed"
        report["passed"] = True
    finally:
        httpx.post = original_post
        report["requests"] = len(calls)
        report["total_recorded_cost_usd"] = ledger["actual_usd"]
        suffix = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        (checks / f"{args.tag.replace('/', '-')}-{args.scenario}-{suffix}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
