"""Session memory (backend v2, section E): conversation lines, steps and one-line task
summaries, persisted to data/session.json after every write."""

import json
import os
import tempfile
import time
from pathlib import Path

MAX_TASKS = 50


class Memory:
    def __init__(self, path: str = "data/session.json"):
        self.path = Path(path)
        self.tasks: list[dict] = []  # finished tasks, oldest first
        self.current: dict | None = None  # {request, mode, chat: [...], steps: [...]}
        self._load()

    # -- writes -------------------------------------------------------------------------------

    def start_task(self, request: str, mode: str) -> None:
        if self.current and self.current["request"]:
            self._close(self.current, "(not finished)")
        chat = self.current["chat"] if self.current else []  # keep lines said before the task
        self.current = {"request": request, "mode": mode, "chat": chat, "steps": []}
        self._save()

    def add(self, who: str, text: str) -> None:
        if self.current is None:
            self.current = {"request": "", "mode": "", "chat": [], "steps": []}
        self.current["chat"].append({"who": who, "text": text})
        self._save()

    def add_step(self, text: str, status: str) -> None:
        if self.current is None:
            return
        self.current["steps"].append({"text": text, "status": status})
        self._save()

    def finish_task(self, result: str) -> str:
        if self.current is None:
            return ""
        summary = self._close(self.current, result)
        self.current = None
        self._save()
        return summary

    # -- read ---------------------------------------------------------------------------------

    def context(self, max_tasks: int = 5, max_chat: int = 10) -> str:
        parts = []
        if self.tasks and max_tasks > 0:
            lines = [f"- {t['summary']}" for t in self.tasks[-max_tasks:]]
            parts.append("Previous tasks:\n" + "\n".join(lines))
        chat = self.current["chat"][-max_chat:] if self.current and max_chat > 0 else []
        if chat:
            lines = [f"{c['who']}: {c['text']}" for c in chat]
            parts.append("Conversation so far:\n" + "\n".join(lines))
        return "\n\n".join(parts)

    # -- internals ----------------------------------------------------------------------------

    def _close(self, task: dict, result: str) -> str:
        done = sum(1 for s in task["steps"] if s["status"] == "done")
        skipped = len(task["steps"]) - done
        n = f"{done} step{'s' if done != 1 else ''}"
        if skipped:
            n += f", {skipped} skipped"
        summary = f"{task['request']} -> {result} ({n})"
        self.tasks.append({"request": task["request"], "mode": task["mode"],
                           "result": result, "summary": summary, "at": time.time()})
        del self.tasks[:-MAX_TASKS]
        return summary

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text())
            tasks, current = data["tasks"], data["current"]
            if not isinstance(tasks, list) or not (current is None or isinstance(current, dict)):
                raise ValueError("bad shape")
        except (OSError, ValueError, KeyError, TypeError):
            return
        self.tasks = tasks[-MAX_TASKS:]
        self.current = current

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".session-", suffix=".json")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump({"tasks": self.tasks, "current": self.current}, f, ensure_ascii=False,
                          indent=1)
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
