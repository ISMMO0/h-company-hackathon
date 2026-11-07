import json

from brain.memory import MAX_TASKS, Memory


def test_empty_context(tmp_path):
    m = Memory(tmp_path / "data" / "session.json")
    assert m.context() == ""


def test_task_lifecycle_and_context(tmp_path):
    m = Memory(tmp_path / "session.json")
    m.start_task("bold the title", "guide")
    m.add("you", "make the title bold")
    m.add_step("select the title", "done")
    m.add_step("open Format menu", "skipped")
    m.add_step("click Bold", "done")
    m.add("shadow", "Done.")
    assert m.context() == "Conversation so far:\nyou: make the title bold\nshadow: Done."

    summary = m.finish_task("title is bold")
    assert summary == "bold the title -> title is bold (2 steps, 1 skipped)"
    assert m.context() == "Previous tasks:\n- bold the title -> title is bold (2 steps, 1 skipped)"

    m.start_task("do the same for Linus", "do")
    m.add("you", "do the same for Linus")
    assert m.context() == (
        "Previous tasks:\n- bold the title -> title is bold (2 steps, 1 skipped)\n\n"
        "Conversation so far:\nyou: do the same for Linus"
    )


def test_chat_before_start_task_is_kept(tmp_path):
    m = Memory(tmp_path / "session.json")
    m.add("you", "open settings")
    m.start_task("open settings", "guide")
    assert m.context() == "Conversation so far:\nyou: open settings"


def test_unfinished_task_is_closed_on_new_task(tmp_path):
    m = Memory(tmp_path / "session.json")
    m.start_task("first", "guide")
    m.add_step("step", "done")
    m.start_task("second", "guide")
    assert m.context() == "Previous tasks:\n- first -> (not finished) (1 step)"


def test_limits(tmp_path):
    m = Memory(tmp_path / "session.json")
    for i in range(8):
        m.start_task(f"task {i}", "guide")
        m.finish_task("ok")
    m.start_task("now", "guide")
    for i in range(12):
        m.add("you", f"line {i}")
    ctx = m.context(max_tasks=3, max_chat=2)
    assert ctx == (
        "Previous tasks:\n- task 5 -> ok (0 steps)\n- task 6 -> ok (0 steps)\n"
        "- task 7 -> ok (0 steps)\n\nConversation so far:\nyou: line 10\nyou: line 11"
    )


def test_persists_and_reloads(tmp_path):
    path = tmp_path / "nested" / "dir" / "session.json"
    m = Memory(path)
    m.start_task("a", "guide")
    m.add("you", "hi")
    m.finish_task("done")
    m.start_task("b", "do")
    m.add("shadow", "on it")
    assert path.exists()
    assert list(path.parent.iterdir()) == [path]  # no temp file left behind

    m2 = Memory(path)
    assert m2.context() == m.context()
    assert m2.current["request"] == "b"
    assert m2.current["mode"] == "do"


def test_corrupt_file_is_tolerated(tmp_path):
    path = tmp_path / "session.json"
    path.write_text("{not json")
    m = Memory(path)
    assert m.context() == ""
    m.start_task("x", "guide")
    assert json.loads(path.read_text())["current"]["request"] == "x"

    path.write_text(json.dumps({"tasks": "nope", "current": None}))
    assert Memory(path).context() == ""


def test_history_is_capped(tmp_path):
    path = tmp_path / "session.json"
    m = Memory(path)
    for i in range(MAX_TASKS + 10):
        m.start_task(f"t{i}", "guide")
        m.finish_task("ok")
    assert len(m.tasks) == MAX_TASKS
    assert m.tasks[0]["request"] == "t10"
    assert len(json.loads(path.read_text())["tasks"]) == MAX_TASKS
