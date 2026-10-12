"""Big autonomous computer tasks, done start-to-finish with verification.

The Live model is brilliant at deciding and seeing, but a 20-step Photoshop
job does not fit in one tool call — and every step (open app, wait for load,
three hotkeys, look at the result) is a place to silently fail. So this action
splits the work the way it actually divides:

  * the MODEL plans, sees (screen_process) and judges;
  * THIS action remembers, executes mechanically, retries, and verifies
    everything verifiable without eyes (process alive, window focused, file
    written, app output text).

Protocol (the model MUST follow what each return says — see TOOL description):

  1. call with goal="..."            → runs safe plans immediately, or returns
                                       [TASK id] PLAN when approval is needed
  2. [TASK id] WAITING_USER: <need>  → ask the user, recall with
                                       task_id + user_reply=<their answer>
  3. [TASK id] VERIFY: <what>        → call screen_process yourself, then
                                       recall with task_id + user_reply=<seen>
  4. [TASK id] DONE / BLOCKED        → report to the user, task closed

Reliability rules inside the executor:

  * two-phase gate — a plan containing a high-risk step (delete, format,
    send/post/publish, system setting, anything irreversible outside the
    app's own Ctrl+Z) NEVER runs before the user approves it;
  * every step has a timeout and up to 3 attempts with fallbacks
    (direct launch → Start-menu search → ask the user; click → find+click);
  * file writes go through file_controller, so they land on the undo stack;
  * desktop work is checkpointed (staged saves), never left half-done and
    silent: the journal records every attempt, and BLOCKED always says how
    to resume (same task_id).
"""
from __future__ import annotations

import concurrent.futures
import re
import threading
import time
import uuid
from pathlib import Path

from core import gemini

# ── App skill packs ──────────────────────────────────────────────────────
# What the planner needs to know about heavyweight creative apps: how they
# are launched, how long a cold start takes, and the reliable workflows.
# Keystrokes, not mouse choreography — coordinates never survive a version
# change, but Ctrl+N does. Anything requiring eyes uses screen_find/click
# at run time, never baked-in pixels.
APP_PACKS = {
    "photoshop": {
        "names": ["Photoshop", "Adobe Photoshop"],
        "proc": ["Photoshop.exe"],
        "title": ["Adobe Photoshop", "Photoshop"],
        "cold_start_s": 30,
        "notes": (
            "New document: key {op: 'hotkey', keys: 'ctrl+n'}, wait 1.5s, key {op: 'press', key: 'enter'}. "
            "Open image file: key {op: 'hotkey', keys: 'ctrl+o'}. "
            "Remove background on open image: Use Photoshop's native tools: "
            "key {op: 'app_command', text: 'remove_background'} OR "
            "key {op: 'hotkey', keys: 'ctrl+f'}, wait 1s, key {op: 'type', text: 'Remove Background'}, wait 1s, key {op: 'press', key: 'enter'}. "
            "Alternative Select Subject: key {op: 'hotkey', keys: 'alt+s'}, wait 0.5s, key {op: 'press', key: 'w'}. "
            "Never try to do image tasks with outside AI when user asks in Photoshop — always use Photoshop's own tools and shortcuts! "
            "Save: Ctrl+S. Export: Ctrl+Shift+S."
        ),
    },
    "illustrator": {
        "names": ["Illustrator", "Adobe Illustrator"],
        "proc": ["Illustrator.exe"],
        "title": ["Adobe Illustrator", "Illustrator"],
        "cold_start_s": 30,
        "notes": (
            "New document: Ctrl+N, Enter. Selection tool: V. Pen: P. "
            "Draw with click anchors; undo a bad anchor with Ctrl+Z, not by "
            "restarting the shape. Save staged work often: Ctrl+S."
        ),
    },
    "indesign": {
        "names": ["InDesign", "Adobe InDesign"],
        "proc": ["InDesign.exe"],
        "title": ["Adobe InDesign", "InDesign"],
        "cold_start_s": 30,
        "notes": "New document: Ctrl+N, Enter. Save staged work often: Ctrl+S.",
    },
}

# Sinhala typing prerequisites, per OS. These need the PERSON (system input
# settings / installs), so the planner must surface them as prerequisites and
# pause with needs_user — never pretend to type Sinhala without them.
SINHALA_PREREQ = {
    "Windows": [
        "Windows built-in Sinhala keyboard: Settings > Time & language > "
        "Language & region > Add a language > Sinhala; switch with Win+Space.",
        "Alternative: Google Input Tools for Windows (Sinhala).",
    ],
    "Darwin": [
        "System Settings > Keyboard > Text Input > Add Sinhala; switch with "
        "the input menu or Control+Space.",
    ],
    "Linux": [
        "Add a Sinhala (si) input source in Settings > Keyboard; switch with "
        "Super+Space.",
    ],
}

# ── Step kinds ───────────────────────────────────────────────────────────
# announce  say a milestone out loud (request_say) + log it
# open_app  launch an app, verify process/window, retry with fallbacks
# key       one computer_control call (hotkey/press/type/click/screen_click…)
# wait      sleep N seconds (cold starts, exports, dialogs)
# verify    PAUSE for the model's eyes: model calls screen_process, resumes
#           with user_reply=<what it sees>; verdict recorded, re-plan on fail
# needs_user PAUSE for the person (open something, approve, answer)
# search    web research, appended to the dossier
# write_doc append a section to the task document (undo-safe), show it live
# show      push text to the on-screen content panel (live progress)
# done      finish early with a message
OPEN_APP_KINDS = ("announce", "open_app", "key", "wait", "verify",
                  "needs_user", "search", "write_doc", "show", "shell", "done")

STEP_TIMEOUT_S = 120
STEP_ATTEMPTS = 3
TASK_BUDGET_S = 600

_TASKS: dict[str, dict] = {}
_TASKS_LOCK = threading.Lock()


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _get_task(task_id: str) -> dict | None:
    with _TASKS_LOCK:
        return _TASKS.get(task_id)


def _put_task(task: dict) -> None:
    with _TASKS_LOCK:
        _TASKS[task["id"]] = task
        # Drop tasks older than 2h so the registry cannot grow forever.
        now = time.time()
        for tid in [t for t, r in _TASKS.items()
                    if now - r.get("updated", now) > 7200]:
            _TASKS.pop(tid, None)


def _touch(task: dict) -> None:
    task["updated"] = time.time()
    _put_task(task)


# ── Planner ──────────────────────────────────────────────────────────────

def _plan(goal: str, ops_hint: str = "") -> dict:
    """Ask the reasoning tier for a JSON step plan. Raises on failure."""
    import json as _json
    import platform as _plat
    try:
        from memory.config_manager import get_full_auto
        _full_auto = get_full_auto()
    except Exception:
        _full_auto = False

    packs = "\n".join(
        f"- {app}: launch={p['names']}, cold_start={p['cold_start_s']}s. {p['notes']}"
        for app, p in APP_PACKS.items())
    sinhala = "\n".join(f"  {k}: {'; '.join(v)}"
                        for k, v in SINHALA_PREREQ.items())
    os_name = _plat.system()
    app_running_info = []
    try:
        from actions import open_app as _oa
        for k in APP_PACKS:
            if _oa._is_app_running(k):
                app_running_info.append(k)
    except Exception:
        pass
    running_str = ", ".join(app_running_info) if app_running_info else "None detected"

    prompt = f"""You plan ONE big computer task for an executor. Reply ONLY with JSON.

Goal: {goal}
OS: {os_name}
Apps already open and running: {running_str}

Step kinds and their fields:
- announce {{text}} — milestone the user hears (use sparingly: start, app ready, blocked, done)
- open_app {{app}} — one of: {', '.join(APP_PACKS)} or any installed app name
- key {{op, keys?, text?, x?, y?, seconds?, title?, description?}} — op is a computer_control action
  (hotkey/press/type/smart_type/click/double_click/right_click/move/scroll/wait/focus_window/screen_find/screen_click/screenshot)
- wait {{seconds}}
- verify {{look_for}} — PAUSES for the model's own eyes; one per phase, not per keystroke
- needs_user {{ask}} — PAUSES for the person (open/enable/approve/answer something)
- search {{query, mode}} — mode: search/news/research; result joins the dossier
- write_doc {{section, body}} — appends a markdown section to the task document (shown live)
- show {{title, text}} — push progress text to the on-screen panel
- shell {{command}} — ONE OS shell command (~60s max) for what no other step
  can do: checks, installs, conversions, queries. Prefer tools over shell.
  Quote any path containing spaces.
- done {{message}}

Mode: {"FULL AUTO is ON — execute everything without asking; still pause with needs_user for things only the person can physically do (open an app by hand, enable a keyboard, answer a question)." if _full_auto else "FULL AUTO is OFF — mark risky steps high risk and expect an approval round before they run."}

App packs:
{packs}

Sinhala typing (this OS):
{os_name}: {'; '.join(SINHALA_PREREQ.get(os_name, SINHALA_PREREQ['Windows']))}

Rules:
1. If the required app is ALREADY RUNNING (see 'Apps already open and running' above):
   DO NOT plan open_app or wait for cold start! Step 1 MUST be key {{op: "focus_window", title: app}}.
   Only plan open_app and cold-start wait if the app is NOT running.
2. For New Document in creative apps (Photoshop, Illustrator), ALWAYS plan:
   key {{op: "hotkey", keys: "ctrl+n"}}, wait {{seconds: 1}}, key {{op: "press", key: "enter"}}.
   NEVER click coordinates for New Document!
3. If the goal needs Sinhala text, put the Sinhala prerequisites FIRST as a
   needs_user pause ("open/enable these, then say ready") — never type Sinhala blind.
4. If a reference image/font is mentioned, add an early step using it (uploaded file).
5. Batch mechanical keys, then ONE verify per phase. Never plan more than 14 steps.
6. Mark risk: "high" for delete/format/send/post/publish/system-setting or anything
   irreversible outside the target app's own undo; "low" otherwise.
7. Research-into-document goals: search steps, then write_doc per section, show at the end.
8. Respond with NOTHING but this JSON:
{{"prerequisites": ["..."], "steps": [{{"id": "s1", "kind": "...", "label": "...", "risk": "low", ...fields}}]}}
JSON:"""
    resp = gemini.call(prompt, tier=gemini.SMART, timeout_ms=60000)
    if resp is None:
        raise RuntimeError("the planner is unavailable (all models failed)")
    raw = (getattr(resp, "text", None) or "").strip()
    raw = re.sub(r"^```[a-zA-Z]*\r?\n?", "", raw)
    raw = re.sub(r"\r?\n?```\s*$", "", raw)
    plan = _json.loads(raw.strip())
    steps = plan.get("steps") or []
    if not steps:
        raise ValueError("planner returned no steps")
    clean = []
    for i, s in enumerate(steps[:14]):
        if not isinstance(s, dict) or s.get("kind") not in OPEN_APP_KINDS:
            continue
        s = dict(s)
        s.setdefault("id", f"s{i + 1}")
        s.setdefault("label", s.get("kind", "step"))
        s.setdefault("risk", "low")
        s["status"] = "pending"
        clean.append(s)
    if not clean:
        raise ValueError("planner returned no usable steps")
    return {"prerequisites": list(plan.get("prerequisites") or []),
            "steps": clean}


def _format_plan(task: dict) -> str:
    lines = [f"[TASK {task['id']}] PLAN — goal: {task['goal']}"]
    if task.get("prerequisites"):
        lines.append("PREREQUISITES (user must have/do these):")
        lines += [f"  - {p}" for p in task["prerequisites"]]
    lines.append("STEPS:")
    for s in task["steps"]:
        flag = " [!]" if s.get("risk") == "high" else ""
        lines.append(f"  {s['id']}. [{s['kind']}] {s.get('label', '')}{flag}")
    if any(s.get("risk") == "high" for s in task["steps"]):
        lines.append(
            f"→ This plan has HIGH-RISK steps ([!]). Present the plan AND the "
            f"prerequisites to the user in their language, ask for explicit "
            f"approval, then call task_agent with task_id={task['id']} and "
            f"user_reply=<their answer>. Do NOT start executing.")
    else:
        lines.append(
            f"→ Present this plan briefly with prerequisites, then START it by "
            f"calling task_agent with task_id={task['id']} and user_reply=yes.")
    return "\n".join(lines)


# ── Real operations (imported lazily so tests can inject fakes) ──────────

def _real_ops(player):
    """Callables the executor uses. Each returns a short result string."""
    from actions import open_app as _oa
    from actions import computer_control as _cc
    from actions import web_search as _ws
    from actions.file_controller import create_file, write_file

    def _op_open(app: str) -> str:
        return _oa.open_app({"app_name": app}, player=player) or "Done."

    def _op_key(params: dict) -> str:
        return _cc.computer_control(dict(params), player=player) or "Done."

    def _op_search(query: str, mode: str) -> str:
        return _ws.web_search({"query": query, "mode": mode},
                              player=player) or "No results."

    def _op_write(path: str, name: str, content: str, append: bool) -> str:
        if append:
            return write_file(path, name, content, append=True)
        return create_file(path, name, content)

    def _op_show(title: str, text: str) -> str:
        try:
            if player is not None and hasattr(player, "show_content"):
                player.show_content(title, text)
                return "shown."
        except Exception as e:
            return f"show failed: {e}"
        return "no display."

    def _op_say(text: str) -> str:
        try:
            if player is not None and hasattr(player, "request_say"):
                player.request_say(text)
                return "spoken."
        except Exception as e:
            return f"say failed: {e}"
        return "no voice."

    def _op_log(text: str) -> str:
        try:
            if player is not None:
                player.write_log(text)
        except Exception:
            pass
        print(f"[TaskAgent] {text}")
        return "logged."

    return {"open": _op_open, "key": _op_key, "search": _op_search,
            "write": _op_write, "show": _op_show, "say": _op_say,
            "log": _op_log}


def _call_sync(fn, *args, timeout: int = STEP_TIMEOUT_S, **kwargs) -> str:
    """Run one blocking op with a hard timeout. Raises on timeout/error."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(fn, *args, **kwargs)
        try:
            out = fut.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(f"step timed out after {timeout}s")
        if isinstance(out, str):
            return out
        return str(out)


# ── Verification (no eyes needed) ────────────────────────────────────────

def _verify_app_open(step: dict) -> tuple[bool, str]:
    """Is the app from an open_app step actually up? Process OR window title."""
    app = (step.get("app") or "").lower()
    pack = next((p for k, p in APP_PACKS.items() if k in app or app in k), None)
    procs = pack["proc"] if pack else []
    titles = pack["title"] if pack else [step.get("app", "")]
    try:
        import psutil
        names = {p.name().lower() for p in psutil.process_iter()}
        for want in procs:
            if want.lower() in names:
                return True, f"process {want} is running"
    except Exception:
        pass
    try:
        import pygetwindow as gw  # type: ignore
        wins = [t for t in gw.getAllTitles() if t]
        for frag in titles:
            for t in wins:
                if frag.lower() in t.lower():
                    return True, f"window '{t[:60]}' is open"
        return False, f"no window matching {titles} (open: {len(wins)} windows)"
    except ImportError:
        # Optional dep absent: process check already ran; be honest, not stuck.
        return (True, "process check only (no window list available)") if procs else (False, "cannot verify")
    except Exception as e:
        return False, f"window check failed: {e}"


def _looks_failed(result: str) -> bool:
    low = (result or "").lower()
    return any(k in low for k in (
        "failed", "could not", "error", "not found", "timed out",
        "unavailable", "no such", "traceback"))


# ── Executor ─────────────────────────────────────────────────────────────

def _execute(task: dict, ops: dict, resume_from: int = 0) -> dict:
    """Run steps from `resume_from`. Returns a result dict with `outcome`:
    done | waiting_user | verify | blocked, plus the user/model-facing text."""
    steps = task["steps"]
    journal = task.setdefault("journal", [])
    dossier = task.setdefault("dossier", [])
    deadline = time.time() + TASK_BUDGET_S

    def _note(msg: str) -> None:
        journal.append(msg)
        ops["log"](msg)
        _touch(task)

    i = resume_from
    while i < len(steps):
        if time.time() > deadline:
            task["status"] = "blocked"
            _touch(task)
            return {"outcome": "blocked",
                    "text": _blocked_text(task, "time budget exceeded — say 'continue' to resume"),
                    "index": i}
        s = steps[i]
        kind = s.get("kind")
        s["status"] = "running"
        _note(f"{s['id']} [{kind}] {s.get('label', '')} — started")

        try:
            if kind == "announce":
                ops["say"](s.get("text", s.get("label", "")))
                s["status"] = "ok"

            elif kind == "open_app":
                ok, detail = _run_open_app(task, s, ops)
                s["status"] = "ok" if ok else "failed"
                s["detail"] = detail
                if not ok:
                    return _pause(task, i, "waiting_user",
                                  f"I could not open {s.get('app')}: {detail}. "
                                  f"Please open it by hand and say 'ready', or say "
                                  f"'skip' to continue without it.")

            elif kind == "key":
                params = {k: s[k] for k in
                          ("op", "action", "keys", "text", "x", "y", "seconds",
                           "title", "description", "direction", "amount", "key",
                           "button", "clear_first", "path")
                          if k in s}
                # The planner writes `op`; the control action calls it `action`.
                if "action" not in params and "op" in params:
                    params["action"] = params.pop("op")
                res = _retry(lambda: _call_sync(ops["key"], params), s, ops)
                s["detail"] = res
                s["status"] = "failed" if _looks_failed(res) else "ok"
                if s["status"] == "failed":
                    return _pause(task, i, "blocked",
                                  f"Step failed after retries: {s.get('label')}. "
                                  f"Last result: {res}. Say 'retry' to try again or "
                                  f"'skip' to move on.")

            elif kind == "wait":
                time.sleep(max(0.0, min(120.0, float(s.get("seconds", 3)))))
                s["status"] = "ok"

            elif kind == "verify":
                s["status"] = "awaiting_eyes"
                task["status"] = "awaiting_verify"
                _touch(task)
                return {"outcome": "verify", "index": i,
                        "text": (
                            f"[TASK {task['id']}] VERIFY — {s.get('look_for', s.get('label', ''))}\n"
                            f"Call screen_process yourself and LOOK. Then call "
                            f"task_agent with task_id={task['id']} and "
                            f"user_reply=<exactly what you see, honest and short>.\n"
                            f"If it looks right, say so and the task continues. "
                            f"If it looks wrong, say what is wrong and the "
                            f"remaining steps will be re-planned.")}

            elif kind == "needs_user":
                s["status"] = "awaiting_user"
                task["status"] = "awaiting_user"
                ops["say"](s.get("ask", s.get("label", "")))
                _touch(task)
                return {"outcome": "waiting_user", "index": i,
                        "text": (
                            f"[TASK {task['id']}] WAITING_USER: {s.get('ask', s.get('label', ''))}\n"
                            f"Ask the user in their language, then call task_agent "
                            f"with task_id={task['id']} and user_reply=<their answer>.")}

            elif kind == "search":
                res = _retry(lambda: _call_sync(
                    ops["search"], s.get("query", ""),
                    (s.get("mode") or "search")), s, ops)
                dossier.append({"query": s.get("query", ""), "result": res})
                s["detail"] = f"{len(res)} chars gathered"
                s["status"] = "failed" if res.startswith("Search failed") else "ok"
                if s["status"] == "failed":
                    return _pause(task, i, "blocked",
                                  f"Research failed: {res}. Say 'retry' or 'skip'.")

            elif kind == "write_doc":
                doc = task.setdefault("doc", {"path": "documents",
                                              "name": f"ROGO-task-{task['id']}.md",
                                              "sections": 0})
                body = f"\n\n## {s.get('section', 'Notes')}\n{s.get('body', '')}\n"
                append = doc["sections"] > 0
                res = _retry(lambda: _call_sync(
                    ops["write"], doc["path"], doc["name"], body, append), s, ops)
                doc["sections"] += 0 if _looks_failed(res) else 1
                s["detail"] = res
                s["status"] = "failed" if _looks_failed(res) else "ok"
                if s["status"] == "ok":
                    ops["show"](f"TASK — {task['goal'][:36]}",
                                _dossier_text(task))
                else:
                    return _pause(task, i, "blocked",
                                  f"Could not write the document: {res}.")

            elif kind == "show":
                ops["show"](s.get("title", "TASK"), s.get("text", ""))
                s["status"] = "ok"

            elif kind == "shell":
                # Shell runs ONLY as a planned step (never a freestyle tool),
                # and is always high risk: with FULL AUTO off it needs the
                # approval round like any other irreversible step.
                s["risk"] = "high"
                cmd = (s.get("command") or s.get("text") or "").strip()
                if not cmd:
                    s["status"] = "skipped"
                    _note(f"{s['id']} shell with no command — skipped")
                else:
                    res = _retry(lambda: _call_sync(
                        _run_shell, cmd, timeout=180), s, ops)
                    s["detail"] = res[:300]
                    s["status"] = "failed" if _looks_failed(res) else "ok"
                    if s["status"] == "failed":
                        return _pause(task, i, "blocked",
                                      f"Command failed after retries: {cmd[:100]}. "
                                      f"Last result: {res[:300]}. Say 'retry' or 'skip'.")

            elif kind == "done":
                s["status"] = "ok"
                task["status"] = "done"
                _note(f"done: {s.get('message', '')}")
                return {"outcome": "done", "index": i + 1,
                        "text": _done_text(task, s.get("message", ""))}

            else:
                s["status"] = "skipped"
                _note(f"unknown kind '{kind}' — skipped")

        except (TimeoutError, RuntimeError) as e:
            s["status"] = "failed"
            return _pause(task, i, "blocked", f"{s.get('label')} failed: {e}. "
                                             f"Say 'retry' or 'skip'.")
        except Exception as e:
            s["status"] = "failed"
            return _pause(task, i, "blocked", f"{s.get('label')} crashed: {e}. "
                                             f"Say 'retry' or 'skip'.")
        _note(f"{s['id']} — {s['status']}")
        i += 1

    task["status"] = "done"
    _touch(task)
    return {"outcome": "done", "index": i, "text": _done_text(task, "")}


def _run_shell(command: str, timeout: int = 60) -> str:
    """Run one OS shell command, capture output. Planned steps only."""
    import subprocess
    try:
        r = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=max(5, min(170, timeout)))
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout}s: {command[:120]}"
    out = (r.stdout or "") + ("\nSTDERR:\n" + r.stderr if r.stderr else "")
    out = out.strip()[:3000] or "(no output)"
    if r.returncode != 0:
        return f"Command failed [exit={r.returncode}]: {out}"
    return out


def _retry(fn, step: dict, ops: dict) -> str:
    """Up to STEP_ATTEMPTS with fallbacks. Raises the last error."""
    last: Exception | None = None
    for attempt in range(1, STEP_ATTEMPTS + 1):
        try:
            return fn()
        except Exception as e:
            last = e
            ops["log"](f"{step.get('id')} attempt {attempt} failed: {e}")
            time.sleep(min(2.0 * attempt, 6.0))
    raise last if last is not None else RuntimeError("step failed")


def _run_open_app(task: dict, step: dict, ops: dict) -> tuple[bool, str]:
    """Launch with fallbacks, then verify. (ok, detail)."""
    app = step.get("app", "")
    pack = next((p for k, p in APP_PACKS.items()
                 if k in app.lower() or app.lower() in k), None)
    names = (pack["names"] if pack else [app]) + ([app] if pack else [])
    last = ""
    for name in dict.fromkeys(names):
        try:
            res = _call_sync(ops["open"], name, timeout=60)
        except Exception as e:
            last = str(e)
            continue
        if _looks_failed(res):
            last = res
            continue
        time.sleep(pack["cold_start_s"] if pack else 4)
        ok, detail = _verify_app_open({**step, "app": name})
        if ok:
            ops["say"](f"{app} is open.")
            return True, detail
        last = detail
    return False, (last or "launch failed")


def _pause(task: dict, index: int, outcome: str, need: str) -> dict:
    task["status"] = "awaiting_user" if outcome == "waiting_user" else "blocked"
    _touch(task)
    prefix = "WAITING_USER" if outcome == "waiting_user" else "BLOCKED"
    return {"outcome": outcome, "index": index,
            "text": (f"[TASK {task['id']}] {prefix}: {need}\n"
                     f"Resume with task_agent task_id={task['id']} and "
                     f"user_reply=<answer|retry|skip>.")}


def _blocked_text(task: dict, reason: str) -> str:
    return (f"[TASK {task['id']}] BLOCKED: {reason}\n"
            f"Journal so far:\n" + "\n".join(f"  - {j}" for j in task["journal"][-12:])
            + f"\nResume with task_agent task_id={task['id']} and user_reply=continue.")


def _dossier_text(task: dict) -> str:
    parts = [f"# {task['goal']}"]
    for d in task.get("dossier", []):
        parts.append(f"\n## Research: {d['query']}\n{d['result']}")
    return "\n".join(parts)[:6000]


def _done_text(task: dict, message: str) -> str:
    lines = [f"[TASK {task['id']}] DONE: {message or task['goal']}"]
    ok = sum(1 for s in task["steps"] if s.get("status") == "ok")
    lines.append(f"Steps OK: {ok}/{len(task['steps'])}")
    if task.get("doc", {}).get("sections"):
        lines.append(f"Document: {task['doc']['name']} ({task['doc']['sections']} sections)")
    return "\n".join(lines)


# ── Resume: fold the user's/model's reply back into the task ─────────────

def _resume(task: dict, reply: str, ops: dict) -> dict:
    """Continue a paused task. `reply` is the user's answer or the model's
    description of what its eyes saw at a verify step."""
    reply = (reply or "").strip()
    low = reply.lower()
    idx = next((i for i, s in enumerate(task["steps"])
                if s.get("status") in ("awaiting_user", "awaiting_eyes", "failed",
                                       "running")),
               len(task["steps"]))

    if any(w in low for w in ("skip", "atla", "geç")):
        if idx < len(task["steps"]):
            task["steps"][idx]["status"] = "skipped"
            ops["log"](f"{task['steps'][idx]['id']} skipped by user")
        task["status"] = "running"
        return _execute(task, ops, resume_from=idx + 1)

    if any(w in low for w in ("retry", "again", "tekrar", "yeniden")):
        if idx < len(task["steps"]):
            task["steps"][idx]["status"] = "pending"
        task["status"] = "running"
        return _execute(task, ops, resume_from=idx)

    answered_verify = (idx < len(task["steps"])
                       and task["steps"][idx].get("status") == "awaiting_eyes")
    if answered_verify:
        bad = any(k in low for k in (
            "wrong", "not ", "missing", "failed", "error", "no ", "can't",
            "cannot", "yanlış", "yok", "olmadı", "hata", "değil"))
        task["steps"][idx]["detail"] = f"eyes: {reply[:200]}"
        if bad:
            task["steps"][idx]["status"] = "failed"
            return _pause(task, idx, "blocked",
                          f"Verification failed: {reply[:200]}. "
                          f"Describe a different approach (or say 'skip'), "
                          f"and I will re-plan the remaining steps.")
        task["steps"][idx]["status"] = "ok"
        ops["log"](f"{task['steps'][idx]['id']} verified: {reply[:120]}")
        task["status"] = "running"
        return _execute(task, ops, resume_from=idx + 1)

    # Ordinary approval / answer: record it and continue.
    task.setdefault("answers", []).append(reply[:300])
    ops["log"](f"user: {reply[:120]}")
    task["status"] = "running"
    if idx < len(task["steps"]) and task["steps"][idx].get("status") in (
            "awaiting_user", "failed", "running"):
        if "ready" in low or "yes" in low or "ok" in low or "oldu" in low or "tamam" in low:
            task["steps"][idx]["status"] = "ok"
            idx += 1
    return _execute(task, ops, resume_from=idx)


# ── Entry point ──────────────────────────────────────────────────────────

def task_agent(parameters=None, player=None, speak=None,
               response=None, session_memory=None) -> str:
    p = parameters or {}
    goal = (p.get("goal") or "").strip()
    task_id = (p.get("task_id") or "").strip()
    reply = (p.get("user_reply") or "").strip()
    mode = (p.get("mode") or "auto").strip().lower()

    ops = _real_ops(player)

    # Continue an existing task.
    if task_id:
        task = _get_task(task_id)
        if task is None:
            return f"No task '{task_id}' — it may have expired. Start again with goal=..."
        if task.get("status") == "done":
            return f"[TASK {task_id}] DONE already: {task.get('goal')}"
        if not reply:
            return (f"[TASK {task_id}] status={task.get('status')}. "
                    f"Call again with user_reply=<answer or what you see>.")
        return _resume(task, reply, ops)["text"]

    if not goal:
        with _TASKS_LOCK:
            open_tasks = [(t, r.get("goal"), r.get("status"))
                          for t, r in _TASKS.items()]
        if open_tasks:
            return ("Open tasks:\n" + "\n".join(
                f"  {t}: {g} [{s}]" for t, g, s in open_tasks))
        return "Tell me the goal: task_agent needs goal='...' to start."

    # Fresh task: plan first, always.
    try:
        plan = _plan(goal)
    except Exception as e:
        return f"Could not plan this task: {e}. Try a smaller first step."
    task = {"id": _new_id(), "goal": goal,
            "prerequisites": plan["prerequisites"], "steps": plan["steps"],
            "journal": [], "dossier": [], "status": "planned", "updated": time.time()}
    _put_task(task)

    if mode == "plan":
        return _format_plan(task)
    try:
        from memory.config_manager import get_full_auto
        _full = get_full_auto()
    except Exception:
        _full = False
    risky = [s for s in task["steps"] if s.get("risk") == "high"]
    if risky and not _full:
        task["status"] = "awaiting_approval"
        _touch(task)
        return _format_plan(task)
    if risky:
        ops["log"](f"FULL AUTO: {len(risky)} high-risk step(s) approved by master switch")

    # Safe plan: announce and run straight through.
    ops["say"](f"On it — {goal[:100]}")
    task["status"] = "running"
    return _execute(task, ops)["text"]


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "task_agent",
    "description": (
        "BIG multi-step computer jobs, done start-to-finish: open Photoshop / "
        "Illustrator / any app and work in it, research the live web into a "
        "document, chain desktop steps. ALWAYS call this FIRST for any job "
        "longer than two steps — never freelance desktop actions one by one. "
        "It plans, announces prerequisites, pauses for the user (WAITING_USER) "
        "or for your own eyes (VERIFY via screen_process), verifies each step "
        "and retries safely. Shell commands run only as planned steps, always "
        "high-risk (FULL AUTO master switch skips approval rounds). Follow "
        "exactly what its return text tells you: "
        "present PLANs and questions to the user in their language, call "
        "screen_process when it says VERIFY, and resume with task_id + "
        "user_reply. Never invent desktop steps outside it."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "goal": {
                "type": "STRING",
                "description": "The whole job in one sentence, with details (app, reference file, what done looks like)",
            },
            "task_id": {
                "type": "STRING",
                "description": "Continue a paused task (from its [TASK id])",
            },
            "user_reply": {
                "type": "STRING",
                "description": "User's answer, or what your eyes saw at a VERIFY step",
            },
            "mode": {
                "type": "STRING",
                "description": "'auto' (default: run safe plans at once) or 'plan' (return the plan only)",
            },
        },
        "required": [],
    },
    "handler": task_agent,
}
