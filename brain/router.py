"""What did the person mean? Routes each utterance, and merges web how-tos into one playbook.

Uses a small OpenAI model when OPENAI_API_KEY is set (more robust on real speech), with a
keyword fallback otherwise. Never called inside the step loop: only when the person speaks
and once at task start.
"""

import json
import os
import re

from dotenv import load_dotenv
from openai import OpenAI

_client: OpenAI | None = None
_model: str | None = None

IDLE_INTENTS = ("answer", "guide", "do", "resume", "unclear")
BUSY_INTENTS = ("stop", "ahead", "wait", "question", "guide", "do", "update", "new_task")


def enabled() -> bool:
    """True once OPENAI_API_KEY is in .env; re-reads .env so a key added later works without a restart."""
    if not os.environ.get("OPENAI_API_KEY"):
        load_dotenv(override=False)
    return bool(os.environ.get("OPENAI_API_KEY"))


def client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=6, max_retries=0)
    return _client


def model() -> str:
    """OPENAI_MODEL if set, else the newest small 'gpt-*-mini' text model the key can use."""
    global _model
    if _model is None:
        _model = os.environ.get("OPENAI_MODEL", "")
        if not _model:
            skip = ("audio", "realtime", "tts", "transcribe", "search", "image", "codex")
            names = sorted(m.id for m in client().models.list()
                           if m.id.startswith("gpt-") and "mini" in m.id and not any(s in m.id for s in skip))
            _model = names[-1] if names else "gpt-4o-mini"
    return _model


def _ask(system: str, user: str) -> dict:
    resp = client().chat.completions.create(
        model=model(), response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    return json.loads(resp.choices[0].message.content or "{}")


# --- routing ----------------------------------------------------------------------------------

ROUTE_PROMPT = """You route what a person says to Shadow Cursor, a voice assistant with a pink cursor that
helps them use apps on their Mac. Reply with JSON: {"intent": ..., "task": ..., "reply": ...}.

If NO task is running, intent is one of:
- "resume": they want to continue the unfinished task mentioned in the context ("ok continue",
  "go on", "reprends", "on continue"). Only if there IS an unfinished task.
- "unclear": too vague to act on and nothing to resume ("ok", "continue" with no unfinished task).
  Put a short question back to them in "reply".
- "answer": a pure information question that needs no app ("what's the best Italian restaurant near
  Opéra?", "who founded H Company?"). Put the question in "task".
- "guide": they want to be shown how to do something on screen ("show me how…", "how do I…").
- "do": they want it done for them ("do it", "book…", "create…", "fais-le").
For "guide"/"do", rewrite "task" as a short imperative ("Create a product called Shadow Pro at 12 €/month").
When in doubt between answer and guide/do, choose guide.

If a task IS running, intent is one of:
- "stop": they want to stop.
- "ahead": they say they already did it / moved on / are further.
- "wait": they want a pause or are doing something else.
- "question": a question about the current task or screen ("where is the export button?", "what does
  this do?"). Put it in "task".
- "guide" / "do": switch to showing / doing (e.g. "do the rest for me").
- "update": extra info or a change to the current task ("actually make it 12 euros"). Put the
  updated full task in "task".
- "new_task": an unrelated new request. Put it in "task".
"reply" is a very short spoken acknowledgement (max 6 words, same language as the person)."""


def route(text: str, busy: bool, task: str = "", app: str = "", brief: str = "",
          unfinished: str = "") -> dict:
    """{'intent', 'task', 'reply'}. Falls back to keywords without a key or on error."""
    if enabled():
        try:
            if busy:
                ctx = f"Task running: {task!r} in {app}."
            else:
                ctx = f"No task running. Front app: {app}."
                ctx += f" Unfinished task: {unfinished!r}." if unfinished else " No unfinished task."
            if brief:
                ctx += f"\nSession so far:\n{brief}"
            out = _ask(ROUTE_PROMPT, f"{ctx}\nThe person said: {text!r}")
            allowed = BUSY_INTENTS if busy else IDLE_INTENTS
            if out.get("intent") in allowed:
                return {"intent": out["intent"], "task": out.get("task") or text,
                        "reply": out.get("reply") or ""}
        except Exception as e:  # noqa: BLE001 - fall back to keywords
            print(f"router: OpenAI failed, using keywords ({type(e).__name__})", flush=True)
    return route_keywords(text, busy, unfinished)


DO_WORDS = ("do it", "do this", "do the rest", "for me", "fais-le", "fais le", "à ma place",
            "fais-moi", "fais moi")
GUIDE_WORDS = ("show me", "montre", "guide me", "how do i", "how to", "comment")
STOP_PHRASES = {"stop", "stop it", "stop shadow", "arrête", "arrete", "arrête-toi", "cancel",
                "annule", "c'est bon stop"}
AHEAD_WORDS = ("already did", "already done", "i did it", "done that", "déjà fait", "j'ai déjà",
               "c'est fait", "i'm ahead", "moved on")
WAIT_WORDS = ("wait", "attends", "hold on", "pause", "une seconde")
QUESTION_START = re.compile(r"^(what|which|who|where|when|why|is |are |does |do you|how much|how many|"
                            r"quel|quelle|quels|qui|où|ou est|quand|pourquoi|combien|est-ce)", re.IGNORECASE)
ACTION_VERBS = re.compile(r"\b(show|open|go to|click|create|add|book|send|buy|make|set|change|"
                          r"montre|ouvre|va sur|crée|ajoute|réserve|envoie|mets|change)\b", re.IGNORECASE)


RESUME_WORDS = ("continue", "go on", "keep going", "resume", "reprends", "reprend", "on continue",
                "vas-y continue", "la suite")


def route_keywords(text: str, busy: bool, unfinished: str = "") -> dict:
    t = text.lower().strip(" .!?,")
    if not busy and len(t.split()) <= 4 and any(w in t for w in RESUME_WORDS):
        if unfinished:
            return {"intent": "resume", "task": unfinished, "reply": "Let's pick up where we left off."}
        return {"intent": "unclear", "task": text, "reply": "Sure, what should we do?"}
    if busy:
        if t in STOP_PHRASES:
            return {"intent": "stop", "task": text, "reply": ""}
        if any(w in t for w in AHEAD_WORDS):
            return {"intent": "ahead", "task": text, "reply": "OK, let me look."}
        if t.startswith(WAIT_WORDS):
            return {"intent": "wait", "task": text, "reply": "Sure, I'll wait."}
        if any(w in t for w in DO_WORDS):
            return {"intent": "do", "task": text, "reply": "On it."}
        if any(w in t for w in ("show me", "montre", "guide me")):
            return {"intent": "guide", "task": text, "reply": "OK, I'll show you."}
        if QUESTION_START.match(t) or t.endswith("?"):
            return {"intent": "question", "task": text, "reply": ""}
        return {"intent": "update", "task": text, "reply": "Got it."}
    if any(w in t for w in DO_WORDS):
        return {"intent": "do", "task": text, "reply": ""}
    if any(w in t for w in GUIDE_WORDS):
        return {"intent": "guide", "task": text, "reply": ""}
    informational = QUESTION_START.match(t) or any(w in t for w in ("best", "meilleur", "recommend"))
    if informational and not ACTION_VERBS.search(t):
        return {"intent": "answer", "task": text, "reply": ""}
    return {"intent": "guide", "task": text, "reply": ""}


# --- playbook merge ---------------------------------------------------------------------------

MERGE_PROMPT = """You turn web how-to notes into a precise playbook for ONE task on a Mac.
Reply with JSON: {"steps": [{"action_hint": ..., "target": ..., "why": ...}], "app": ...}.
3 to 8 steps. action_hint: what to do, imperative, a few words. target: the exact UI element (label and
usual position). why: a few words a beginner understands. "app": the app or website to use.
Drop steps that don't apply to this exact task; don't invent menus that aren't in the notes unless
you are sure."""


def merge_playbook(task: str, app: str, steps: list[dict], note: str = "") -> list[dict]:
    """Clean the Linkup steps for this exact task. Returns the input on any failure."""
    if not enabled() or not steps:
        return steps
    try:
        out = _ask(MERGE_PROMPT, json.dumps({"task": task, "front_app": app, "notes": steps,
                                             "tip": note}, ensure_ascii=False))
        merged = [s for s in out.get("steps", []) if isinstance(s, dict) and s.get("action_hint")]
        return merged[:8] or steps
    except Exception:  # noqa: BLE001
        return steps


# --- session brief ----------------------------------------------------------------------------

BRIEF_PROMPT = """You keep the memory of a voice assistant that helps one person use apps on their Mac.
From the session log, write a short brief (max 6 lines) that another model will read before each
request: what the person is working on, which apps/sites, what was done and what is unfinished,
their preferences (language, guide vs do). Plain facts, no advice. Reply with JSON {"brief": ...}."""


def session_brief(log: str) -> str:
    """GPT rewrite of the session log into a short brief ('' if unavailable)."""
    if not enabled() or not log:
        return ""
    try:
        return str(_ask(BRIEF_PROMPT, log).get("brief", ""))[:800]
    except Exception:  # noqa: BLE001
        return ""
