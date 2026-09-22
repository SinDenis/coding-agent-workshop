# Свой кодинговый агент

Две части: агентский цикл и Plan Mode. Python, OpenRouter, обычный терминал.
Агент написан в одном `agent.py`, без агентского фреймворка. В начальном коммите
агента ещё нет: сначала познакомьтесь с задачей, которую он будет решать.

## Начать

Нужны Git и [uv](https://docs.astral.sh/uv/getting-started/installation/).
Поддерживаемый учебный путь: macOS/Linux, Windows через WSL. Python 3.11 выбирает uv.

```sh
uv sync --locked
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run python prepare_demo.py
```

Последняя команда создаёт новую копию трекера в `.runs/` и печатает её путь.
Повторный запуск создаёт ещё одну копию, ничего не удаляет.

Для запросов к модели скопируйте `.env.example` в `.env`, добавьте свой ключ OpenRouter.
Ключ нужен только для реальных запросов. Автотестам он не нужен.
Установите лимит расходов отдельного ключа в OpenRouter, например $5.

## Навигация

Читайте [SEMINAR.md](SEMINAR.md): самостоятельный практикум с кодом, командами и проверками.
Начало: `git switch --detach step-00-start`. Финал: `git switch main`.
Не переключайтесь с несохранёнными собственными правками: сохраните их в своей ветке
или stash. Команды reset/clean для практикума не нужны.

## Безопасность

`shell` выполняет команды локально с вашими правами. Это **не песочница**.
Рабочая папка не мешает shell обратиться к другим файлам или сети.
Используйте только учебную копию без секретов. Агент может ошибаться и удалять данные.
Не передавайте ему настоящие проекты. В Plan Mode защита строится на инструментах
чтения и проверке разрешений в исполнителе, а не на запрете словами.

## Что здесь намеренно отсутствует

Docker, apply_patch, фоновые сессии, MCP, субагенты, стриминг и production-гарантии.
Тесты трекера из `demo/` намеренно воспроизводят ошибку. Тесты самого агента
из `tests/` должны проходить. Не исправляйте шаблон `demo/`: агент работает в `.runs/`.

## Источники

- [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629)
- [learn-claude-code, S01](https://github.com/shareAI-lab/learn-claude-code/tree/main/s01_agent_loop)
- [OpenRouter: tool calling](https://openrouter.ai/docs/guides/features/tool-calling)
- [OpenRouter: reasoning details](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens)

Это самостоятельная учебная реализация, не копия исходников Claude Code.
