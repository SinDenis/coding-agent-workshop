"""Small in-memory task tracker. One regression is intentionally left for the agent."""

import argparse
import json
import shlex
import sys
from pathlib import Path


def initial_tasks():
    return [
        {"id": 1, "title": "Купить молоко", "done": False},
        {"id": 2, "title": "Позвонить", "done": False},
    ]


def complete(tasks, task_id):
    if not any(task["id"] == task_id for task in tasks):
        raise ValueError(f"Задача {task_id} не найдена")
    tasks[task_id]["done"] = True


def show(tasks):
    print(f"tasks[{len(tasks)}]{{id,title,status}}:")
    for task in tasks:
        title = json.dumps(task["title"], ensure_ascii=False)
        state = "done" if task["done"] else "open"
        print(f"  {task['id']},{title},{state}")
    if not tasks:
        print('message: "Задач пока нет"')


class Parser(argparse.ArgumentParser):
    def error(self, message):
        print(f"error: {json.dumps(message, ensure_ascii=False)}")
        print('help: "python tasks.py --help; флаги: --command, --help"')
        raise SystemExit(2)


def main(argv=None):
    parser = Parser(description="Трекер задач: команды выполняются в памяти одного процесса.")
    parser.add_argument(
        "--command",
        action="append",
        default=[],
        metavar="COMMAND",
        help="Повторяемый: list | add <название> | done <id>. Пример: --command 'done 1'",
    )
    args = parser.parse_args(argv)
    tasks = initial_tasks()
    if not args.command:
        print(f"bin: {json.dumps(str(Path(__file__).resolve()), ensure_ascii=False)}")
        print('description: "Учебный трекер задач без сохранения между запусками"')
        show(tasks)
        print("help: \"python tasks.py --command 'add Новая задача' --command list\"")
        return 0
    for command in args.command:
        try:
            words = shlex.split(command)
            if words == ["list"]:
                show(tasks)
            elif len(words) >= 2 and words[0] == "add":
                task_id = max((task["id"] for task in tasks), default=0) + 1
                tasks.append({"id": task_id, "title": " ".join(words[1:]), "done": False})
                print(f"added: {task_id}")
            elif len(words) == 2 and words[0] == "done":
                complete(tasks, int(words[1]))
                print(f"completed: {words[1]}")
            else:
                raise ValueError("Команды: list | add <название> | done <id>")
        except (ValueError, IndexError) as exc:
            print(f"error: {json.dumps(str(exc), ensure_ascii=False)}")
            print('help: "python tasks.py --help"')
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
