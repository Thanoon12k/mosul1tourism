# ==========================================================
# 🎯 Goals 2026 — Telegram AI Agent (core)
# ----------------------------------------------------------
# Send the bot any messy message ("rubbish" notes, voice-to-text,
# half ideas...). Groq turns it into a clean plan for your
# Goals 2026 board (goals → missions → steps, with emoji, color,
# category, deadline). You get a preview and choose:
#   ✅ Approve  →  the plan is written to the board
#   ✏️ Edit     →  send a correction, the plan is redrafted
#   ❌ Cancel   →  nothing is written
# A monitor sends a daily digest, deadline alerts and the steps
# that got checked on the board since the last digest.
#
# This module is transport-agnostic:
#   • inside the Goals 2026 Flask app → register_flask(app, run_tool)  (webhook)
#   • standalone (app.py)             → call_tool = MCP client, polling loop
# ==========================================================

import json
import html
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone

import requests

HERE = os.path.dirname(os.path.abspath(__file__))


# ==========================================================
# 🔐 SETTINGS (goals_agent.json next to this file, env vars override)
# ==========================================================
def load_settings():
    cfg = {}
    path = os.path.join(HERE, "goals_agent.json")
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            print(f"❌ goals_agent.json: {e}")
    env = {
        "bot_token": "BOT_TOKEN",
        "groq_api_key": "GROQ_API_KEY",
        "groq_model": "GROQ_MODEL",
        "allowed_chat_ids": "ALLOWED_CHAT_IDS",
        "webhook_secret": "WEBHOOK_SECRET",
        "tz_offset_hours": "TZ_OFFSET_HOURS",
        "digest_hour": "DIGEST_HOUR",
        "deadline_alert_days": "DEADLINE_ALERT_DAYS",
        "state_db": "STATE_DB",
    }
    for key, var in env.items():
        if os.environ.get(var):
            cfg[key] = os.environ[var]
    ids = cfg.get("allowed_chat_ids", [])
    if isinstance(ids, str):
        ids = [x for x in ids.replace(" ", "").split(",") if x]
    cfg["allowed_chat_ids"] = [int(x) for x in ids]
    cfg.setdefault("groq_model", "openai/gpt-oss-120b")
    cfg["tz_offset_hours"] = float(cfg.get("tz_offset_hours", 3))       # Iraq = UTC+3
    cfg["digest_hour"] = int(cfg.get("digest_hour", 9))
    cfg["deadline_alert_days"] = int(cfg.get("deadline_alert_days", 3))
    cfg.setdefault("state_db", os.path.join(HERE, "goals_agent_state.db"))
    return cfg


S = load_settings()
TELEGRAM_API = f"https://api.telegram.org/bot{S.get('bot_token', '')}"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
LOCAL_TZ = timezone(timedelta(hours=S["tz_offset_hours"]))
MAX_HISTORY = 10

# The host sets this: call_tool(name, args) -> dict (raises on error)
call_tool = None

stats = {"messages": 0, "plans_drafted": 0, "plans_applied": 0, "last_message": "—", "last_action": "—"}


# ==========================================================
# 💾 STATE (small sqlite key/value store, survives restarts)
# ==========================================================
def _state_conn():
    conn = sqlite3.connect(S["state_db"], timeout=10)
    conn.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
    return conn


def get_state(key, default=None):
    try:
        conn = _state_conn()
        row = conn.execute("SELECT v FROM kv WHERE k = ?", (key,)).fetchone()
        conn.close()
        return json.loads(row[0]) if row else default
    except Exception as e:
        print(f"❌ get_state {key}: {e}")
        return default


def set_state(key, value):
    try:
        conn = _state_conn()
        if value is None:
            conn.execute("DELETE FROM kv WHERE k = ?", (key,))
        else:
            conn.execute("INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)", (key, json.dumps(value, ensure_ascii=False)))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ set_state {key}: {e}")


# ==========================================================
# 🔌 BOARD ACCESS
# ==========================================================
step_names = {}  # step_id -> text, refreshed on every get_board()


def tool(name, args=None):
    if call_tool is None:
        raise RuntimeError("goals_agent.call_tool is not set")
    return call_tool(name, args or {})


def get_board():
    board = tool("get_board")
    for g in board.get("goals", []):
        for m in g.get("missions", []):
            for s in m.get("steps", []):
                step_names[s["id"]] = s["text"]
    return board


def error_text(e):
    return str(getattr(e, "message", "") or e)


# ==========================================================
# 🛠️ ALLOWED TOOLS (what the AI may propose)
# ==========================================================
COLORS = ["ember", "ocean", "forest", "violet", "sun", "rose", "slate", "teal"]

TOOL_ARGS = {
    "create_goal":    ["title", "emoji", "color", "category", "deadline", "why", "missions"],
    "update_goal":    ["goal_id", "title", "emoji", "color", "category", "deadline", "why", "archived", "move"],
    "archive_goal":   ["goal_id"],
    "restore_goal":   ["goal_id"],
    "add_mission":    ["goal_id", "title", "steps"],
    "update_mission": ["mission_id", "title", "move"],
    "add_steps":      ["mission_id", "steps"],
    "check_steps":    ["step_ids", "done"],
    "update_step":    ["step_id", "text", "done", "move"],
    "delete_step":    ["step_id"],
    "delete_mission": ["mission_id"],
    "delete_goal":    ["goal_id"],
}
DANGEROUS_TOOLS = {"delete_step", "delete_mission", "delete_goal"}


def clean_actions(actions):
    """Keep only known tools and known arguments."""
    cleaned = []
    for a in actions or []:
        if not isinstance(a, dict):
            continue
        name = a.get("tool")
        if name not in TOOL_ARGS:
            continue
        args = {k: v for k, v in (a.get("args") or {}).items() if k in TOOL_ARGS[name]}
        if args.get("color") and args["color"] not in COLORS:
            args.pop("color")
        cleaned.append({"tool": name, "args": args, "summary": str(a.get("summary", ""))[:300]})
    return cleaned


# ==========================================================
# 🧠 GROQ PLANNER
# ==========================================================
def compact_board(board):
    """Small text version of the board so the prompt stays short."""
    lines = []
    for g in board.get("goals", []):
        lines.append(
            f"GOAL #{g['id']} {g.get('emoji', '')} {g['title']} | category={g.get('category', '')} "
            f"color={g.get('color', '')} deadline={g.get('deadline', '')} progress={g['progress']['pct']}%"
        )
        for m in g.get("missions", []):
            lines.append(f"  MISSION #{m['id']} {m['title']}")
            for s in m.get("steps", []):
                lines.append(f"    STEP #{s['id']} [{'x' if s['done'] else ' '}] {s['text']}")
    for g in board.get("archived_goals", []):
        lines.append(f"ARCHIVED GOAL #{g.get('id')} {g.get('title', '')}")
    return "\n".join(lines) or "(board is empty)"


PLANNER_PROMPT = """You are the Goals 2026 agent. The user owns a goals board:
each GOAL has an emoji, color, category, optional deadline, a one-line "why", and ordered MISSIONS;
each MISSION is a checklist of short STEPS.

The user sends messy, informal messages (Iraqi Arabic, English or mixed, typos, voice-to-text).
Your job: understand the intent and turn it into a clean plan of board changes.

Today is {today}. Current board:
{board}

Return ONLY a JSON object:
{{
  "reply": "short friendly message to the user, in the SAME language they wrote in, emojis ok",
  "actions": [
    {{"tool": "<tool name>", "args": {{...}}, "summary": "one short line describing this change"}}
  ]
}}

Tools and args:
- create_goal: title, emoji (one emoji), color (one of ember, ocean, forest, violet, sun, rose, slate, teal),
  category (short label e.g. Career, Health, Education), deadline (YYYY-MM-DD or omit), why (one line),
  missions: [{{"title": "...", "steps": ["...", "..."]}}]
- update_goal: goal_id + any of title, emoji, color, category, deadline, why
- archive_goal / restore_goal: goal_id
- add_mission: goal_id, title, steps
- update_mission: mission_id, title
- add_steps: mission_id, steps
- check_steps: step_ids (list), done (true/false)
- update_step: step_id + text and/or done
- delete_step / delete_mission / delete_goal: id (only if the user clearly asks to delete)

Rules:
- Use ids ONLY from the board above. Never invent ids.
- If the message fits an existing goal, add to it instead of creating a duplicate.
- Good missions are 2-5 concrete milestones; good steps are short, actionable, checkable (max ~8 words).
- Write goal/mission/step text in the language the user used.
- Pick a fitting emoji and color; resolve relative dates ("next month", "بعد اسبوعين") to YYYY-MM-DD.
- If the user says they finished something, use check_steps with the matching step ids.
- If the message is only a question about progress, answer in "reply" and return "actions": [].
- If a current draft is given with an edit request, return the FULL revised plan (not only the diff).
"""


def ask_groq_json(messages):
    headers = {"Authorization": f"Bearer {S.get('groq_api_key', '')}", "Content-Type": "application/json"}
    body = {
        "model": S["groq_model"],
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
    }
    r = requests.post(GROQ_URL, headers=headers, json=body, timeout=50)
    if r.status_code != 200:
        raise RuntimeError(f"Groq {r.status_code}: {r.text[:200]}")
    return json.loads(r.json()["choices"][0]["message"]["content"])


def draft_plan(chat_id, user_message, current_draft=None):
    board = get_board()
    today = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d (%A)")
    messages = [{"role": "system", "content": PLANNER_PROMPT.format(today=today, board=compact_board(board))}]
    history = get_state(f"hist:{chat_id}", [])
    messages += history[-MAX_HISTORY:]
    if current_draft:
        messages.append({"role": "user", "content": (
            f"Original message: {current_draft['source']}\n\n"
            f"Current draft plan:\n{json.dumps(current_draft['actions'], ensure_ascii=False)}\n\n"
            f"Edit request: {user_message}"
        )})
    else:
        messages.append({"role": "user", "content": user_message})

    plan = ask_groq_json(messages)
    reply = str(plan.get("reply", "")).strip()
    actions = clean_actions(plan.get("actions"))

    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": reply})
    set_state(f"hist:{chat_id}", history[-MAX_HISTORY:])
    return reply, actions


# ==========================================================
# 🖼️ FORMATTING (Telegram HTML)
# ==========================================================
def esc(text):
    return html.escape(str(text or ""))


def progress_bar(pct, width=10):
    filled = int(round((pct or 0) / 100 * width))
    return "▰" * filled + "▱" * (width - filled)


def format_action(action):
    name, args = action["tool"], action["args"]
    if name == "create_goal":
        lines = [f"🆕 <b>{esc(args.get('emoji', '🎯'))} {esc(args.get('title'))}</b>"]
        meta = []
        if args.get("category"):
            meta.append(f"🏷 {esc(args['category'])}")
        if args.get("color"):
            meta.append(f"🎨 {esc(args['color'])}")
        if args.get("deadline"):
            meta.append(f"📅 {esc(args['deadline'])}")
        if meta:
            lines.append("   " + "  ·  ".join(meta))
        if args.get("why"):
            lines.append(f"   💡 <i>{esc(args['why'])}</i>")
        for i, m in enumerate(args.get("missions") or [], 1):
            lines.append(f"   <b>{i}. {esc(m.get('title'))}</b>")
            for s in m.get("steps") or []:
                lines.append(f"      ☐ {esc(s)}")
        return "\n".join(lines)

    icon = "⚠️ " if name in DANGEROUS_TOOLS else "✏️ "
    text = f"{icon}<b>{esc(name)}</b> — {esc(action.get('summary') or '')}"
    if name in ("add_mission", "add_steps"):
        for s in args.get("steps") or []:
            text += f"\n      ☐ {esc(s)}"
    if name == "check_steps":
        mark = "☑️" if args.get("done", True) else "☐"
        for sid in args.get("step_ids") or []:
            text += f"\n      {mark} {esc(step_names.get(sid, f'step #{sid}'))}"
    return text


def format_draft(draft):
    parts = []
    if draft["reply"]:
        parts.append(esc(draft["reply"]))
    if draft["actions"]:
        parts.append("━━━━━━━━━━━━━━\n📝 <b>الخطة المقترحة / Proposed plan</b>")
        for a in draft["actions"]:
            parts.append(format_action(a))
        parts.append("━━━━━━━━━━━━━━\nوافق، عدّل أو ألغِ 👇")
    return "\n\n".join(parts)


def format_goal(g):
    lines = [
        f"{esc(g.get('emoji', '🎯'))} <b>{esc(g['title'])}</b>  #{g['id']}",
        f"{progress_bar(g['progress']['pct'])} {g['progress']['pct']}%",
    ]
    meta = []
    if g.get("category"):
        meta.append(f"🏷 {esc(g['category'])}")
    if g.get("deadline"):
        meta.append(f"📅 {esc(g['deadline'])}")
    if meta:
        lines.append("  ·  ".join(meta))
    if g.get("why"):
        lines.append(f"💡 <i>{esc(g['why'])}</i>")
    for m in g.get("missions", []):
        p = m["progress"]
        lines.append(f"\n<b>{'✅' if p['complete'] else '🔹'} {esc(m['title'])}</b>  ({p['done']}/{p['total']})")
        for s in m.get("steps", []):
            lines.append(f"   {'☑️' if s['done'] else '☐'} {esc(s['text'])}")
    return "\n".join(lines)


def format_board(board):
    goals = board.get("goals", [])
    lines = [
        "📋 <b>Goals 2026</b>",
        f"{progress_bar(board.get('overall_pct', 0))} {board.get('overall_pct', 0)}%  ·  "
        f"🏆 {board.get('goals_achieved', 0)}/{len(goals)}",
        "",
    ]
    for g in goals:
        dl = f"  📅 {g['deadline']}" if g.get("deadline") else ""
        lines.append(f"{esc(g.get('emoji', '🎯'))} <b>{esc(g['title'])}</b> — {g['progress']['pct']}%{dl}")
    if not goals:
        lines.append("لا توجد أهداف بعد. ارسل لي أي فكرة وأنا أرتبها 🙂")
    return "\n".join(lines)


def next_steps(board, limit=6):
    """First unchecked step of each goal — the 'do this next' list."""
    items = []
    for g in board.get("goals", []):
        for m in g.get("missions", []):
            open_steps = [s for s in m.get("steps", []) if not s["done"]]
            if open_steps:
                items.append(f"{esc(g.get('emoji', '🎯'))} {esc(open_steps[0]['text'])}  <i>({esc(g['title'])})</i>")
                break
    return items[:limit]


def days_left(deadline):
    try:
        return (datetime.strptime(deadline, "%Y-%m-%d").date() - datetime.now(LOCAL_TZ).date()).days
    except Exception:
        return None


def days_label(days):
    if days < 0:
        return f"متأخر {-days} يوم"
    if days == 0:
        return "اليوم!"
    return f"باقي {days} يوم"


# ==========================================================
# 📨 TELEGRAM FUNCTIONS
# ==========================================================
def tg(method, **payload):
    try:
        for key in ("reply_markup",):
            if key in payload and not isinstance(payload[key], str):
                payload[key] = json.dumps(payload[key])
        r = requests.post(f"{TELEGRAM_API}/{method}", data=payload, timeout=30)
        data = r.json()
        if not data.get("ok"):
            print(f"❌ telegram {method}: {data.get('description')}")
        return data
    except Exception as e:
        print(f"❌ telegram {method}: {e}")
        return {}


def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text[:4000], "parse_mode": "HTML", "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return tg("sendMessage", **payload)


def edit_message(chat_id, message_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text[:4000],
               "parse_mode": "HTML", "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return tg("editMessageText", **payload)


def send_typing(chat_id):
    tg("sendChatAction", chat_id=chat_id, action="typing")


def answer_callback(callback_id, text=""):
    tg("answerCallbackQuery", callback_query_id=callback_id, text=text)


# ==========================================================
# ⌨️ INLINE KEYBOARDS
# ==========================================================
def main_menu():
    return {"inline_keyboard": [
        [{"text": "📋 اللوحة / Board", "callback_data": "board"},
         {"text": "👉 التالي / Next", "callback_data": "next"}],
        [{"text": "⏰ المواعيد / Deadlines", "callback_data": "deadlines"},
         {"text": "❓ مساعدة / Help", "callback_data": "help"}],
    ]}


def draft_menu():
    return {"inline_keyboard": [
        [{"text": "✅ موافقة / Approve", "callback_data": "approve"}],
        [{"text": "✏️ تعديل / Edit", "callback_data": "edit"},
         {"text": "❌ إلغاء / Cancel", "callback_data": "cancel"}],
    ]}


def board_menu(board):
    rows = []
    for g in board.get("goals", []):
        rows.append([{"text": f"{g.get('emoji', '🎯')} {g['title'][:40]} · {g['progress']['pct']}%",
                      "callback_data": f"goal:{g['id']}"}])
    rows.append([{"text": "🔄 تحديث / Refresh", "callback_data": "board"}])
    return {"inline_keyboard": rows}


def goal_menu(g):
    rows = []
    for m in g.get("missions", []):
        for s in m.get("steps", []):
            if not s["done"] and len(rows) < 12:
                rows.append([{"text": f"☐ {s['text'][:50]}", "callback_data": f"tick:{s['id']}:{g['id']}"}])
    rows.append([{"text": "⬅️ اللوحة / Board", "callback_data": "board"}])
    return {"inline_keyboard": rows}


# ==========================================================
# 🚀 START / HELP
# ==========================================================
HELP_TEXT = (
    "🤖 <b>Goals 2026 Agent</b>\n\n"
    "ارسل لي أي شي — ملاحظة مكركبة، فكرة، أو شنو خلصت اليوم — وآني أرتبه:\n"
    "• أهداف جديدة مع مهمات وخطوات وإيموجي ولون وموعد\n"
    "• إضافة خطوات لهدف موجود\n"
    "• تأشير الخطوات اللي خلصتها ✅\n\n"
    "قبل أي تغيير أرسلك معاينة: <b>موافقة</b> / <b>تعديل</b> / <b>إلغاء</b>.\n\n"
    "<b>Examples</b>\n"
    "<code>ابي اتعلم انكليزي قبل نهاية السنة ielts 6.5</code>\n"
    "<code>finished paper 2 and the lit review</code>\n"
    "<code>شكد باقي على الماستر؟</code>\n\n"
    "<b>Commands</b>\n"
    "/board — اللوحة\n/next — الخطوات التالية\n/deadlines — المواعيد\n/goal 3 — تفاصيل هدف\n"
    "/cancel — إلغاء المسودة\n/reset — مسح الذاكرة"
)


def handle_start(chat_id, user_name):
    send_message(
        chat_id,
        f"هلا {esc(user_name)} 👋\n\n"
        "آني وكيل <b>Goals 2026</b> 🎯\n"
        "دزلي أي فكرة أو ملاحظة حتى لو مكركبة، وآني أحولها لأهداف ومهمات وخطوات مرتبة، "
        "وأراقب تقدمك وأذكرك بالمواعيد ⏰",
        main_menu(),
    )


# ==========================================================
# 🧩 ACTIONS
# ==========================================================
def show_board(chat_id, message_id=None):
    board = get_board()
    if message_id:
        edit_message(chat_id, message_id, format_board(board), board_menu(board))
    else:
        send_message(chat_id, format_board(board), board_menu(board))


def show_goal(chat_id, goal_id, message_id=None):
    g = tool("get_goal", {"goal_id": int(goal_id)})
    if message_id:
        edit_message(chat_id, message_id, format_goal(g), goal_menu(g))
    else:
        send_message(chat_id, format_goal(g), goal_menu(g))


def show_next(chat_id):
    items = next_steps(get_board())
    text = "👉 <b>الخطوات التالية / Next steps</b>\n\n" + ("\n".join(items) if items else "كلشي مخلص! 🎉")
    send_message(chat_id, text, main_menu())


def show_deadlines(chat_id):
    rows = []
    for g in get_board().get("goals", []):
        days = days_left(g.get("deadline", ""))
        if days is not None and not g["progress"]["complete"]:
            rows.append((days, f"{esc(g.get('emoji', '🎯'))} <b>{esc(g['title'])}</b> — {g['deadline']} "
                               f"({days_label(days)}) · {g['progress']['pct']}%"))
    rows.sort()
    text = "⏰ <b>المواعيد / Deadlines</b>\n\n" + ("\n".join(r[1] for r in rows) if rows else "ماكو مواعيد محددة.")
    send_message(chat_id, text, main_menu())


def apply_draft(chat_id):
    draft = get_state(f"draft:{chat_id}")
    set_state(f"draft:{chat_id}", None)
    set_state(f"edit:{chat_id}", None)
    if not draft or not draft.get("actions"):
        send_message(chat_id, "ماكو مسودة حالياً 🤷")
        return
    results = []
    for a in draft["actions"]:
        try:
            tool(a["tool"], a["args"])
            label = a["args"].get("title") or a.get("summary") or a["tool"]
            results.append(f"✅ {esc(label)}")
        except Exception as e:
            results.append(f"❌ {esc(a['tool'])}: {esc(error_text(e))}")
    stats["plans_applied"] += 1
    stats["last_action"] = f"{datetime.now():%H:%M} applied {len(draft['actions'])} change(s)"
    board = get_board()
    text = "🎉 <b>تم التنفيذ / Done</b>\n\n" + "\n".join(results)
    text += f"\n\n📊 التقدم الكلي: {progress_bar(board.get('overall_pct', 0))} {board.get('overall_pct', 0)}%"
    send_message(chat_id, text, main_menu())


def handle_text(chat_id, text):
    send_typing(chat_id)
    current = get_state(f"draft:{chat_id}") if get_state(f"edit:{chat_id}") else None
    set_state(f"edit:{chat_id}", None)
    try:
        reply, actions = draft_plan(chat_id, text, current)
    except Exception as e:
        print(f"❌ planner error: {e}")
        send_message(chat_id, f"⚠️ صار خطأ: <code>{esc(error_text(e))}</code>\nجرب مرة ثانية.")
        return

    if not actions:
        send_message(chat_id, esc(reply) or "👍", main_menu())
        return

    draft = {"source": current["source"] if current else text, "reply": reply, "actions": actions}
    set_state(f"draft:{chat_id}", draft)
    stats["plans_drafted"] += 1
    send_message(chat_id, format_draft(draft), draft_menu())


# ==========================================================
# 🔘 CALLBACKS
# ==========================================================
def handle_callback(callback):
    data = callback.get("data", "")
    chat_id = callback["message"]["chat"]["id"]
    message_id = callback["message"]["message_id"]
    callback_id = callback["id"]

    if not is_allowed(chat_id):
        answer_callback(callback_id, "⛔")
        return

    try:
        if data == "approve":
            answer_callback(callback_id, "⏳")
            # remove the buttons so the same plan can't be applied twice
            tg("editMessageReplyMarkup", chat_id=chat_id, message_id=message_id,
               reply_markup={"inline_keyboard": []})
            apply_draft(chat_id)
        elif data == "edit":
            answer_callback(callback_id)
            if not get_state(f"draft:{chat_id}"):
                send_message(chat_id, "ماكو مسودة حالياً 🤷")
                return
            set_state(f"edit:{chat_id}", True)
            send_message(chat_id, "✏️ اكتب شنو تريد أغير (مثلاً: <i>خلي الموعد نهاية نوفمبر وضيف خطوة مراجعة</i>)")
        elif data == "cancel":
            set_state(f"draft:{chat_id}", None)
            set_state(f"edit:{chat_id}", None)
            answer_callback(callback_id, "❌")
            edit_message(chat_id, message_id, "❌ انلغت المسودة، ما تغير شي.")
        elif data == "board":
            answer_callback(callback_id)
            show_board(chat_id, message_id)
        elif data.startswith("goal:"):
            answer_callback(callback_id)
            show_goal(chat_id, data.split(":")[1], message_id)
        elif data.startswith("tick:"):
            _, step_id, goal_id = data.split(":")
            tool("check_steps", {"step_ids": [int(step_id)], "done": True})
            answer_callback(callback_id, "✅")
            stats["last_action"] = f"{datetime.now():%H:%M} checked step #{step_id}"
            show_goal(chat_id, goal_id, message_id)
        elif data == "next":
            answer_callback(callback_id)
            show_next(chat_id)
        elif data == "deadlines":
            answer_callback(callback_id)
            show_deadlines(chat_id)
        elif data == "help":
            answer_callback(callback_id)
            send_message(chat_id, HELP_TEXT, main_menu())
        else:
            answer_callback(callback_id)
    except Exception as e:
        print(f"❌ callback error: {e}")
        send_message(chat_id, f"⚠️ خطأ: <code>{esc(error_text(e))}</code>")


# ==========================================================
# 🔒 ACCESS
# ==========================================================
def is_allowed(chat_id):
    return chat_id in S["allowed_chat_ids"]


# ==========================================================
# 📥 UPDATE DISPATCHER (used by webhook and polling)
# ==========================================================
def process_update(update):
    # Telegram retries a webhook that was slow to answer: skip anything already handled
    update_id = update.get("update_id", 0)
    if update_id and update_id <= get_state("last_update_id", 0):
        return
    set_state("last_update_id", update_id)

    if "callback_query" in update:
        handle_callback(update["callback_query"])
        return

    message = update.get("message")
    if not message or "text" not in message:
        return

    chat_id = message["chat"]["id"]
    text = message["text"].strip()
    user_name = message.get("from", {}).get("first_name", "")
    stats["messages"] += 1
    stats["last_message"] = f"{datetime.now():%H:%M} {text[:60]}"

    if not is_allowed(chat_id):
        send_message(chat_id, "⛔ هذا البوت خاص.\n"
                              f"Your chat id: <code>{chat_id}</code>")
        return

    try:
        command = text.split()[0].split("@")[0].lower() if text.startswith("/") else ""
        if command == "/start":
            handle_start(chat_id, user_name)
        elif command == "/help":
            send_message(chat_id, HELP_TEXT, main_menu())
        elif command == "/board":
            show_board(chat_id)
        elif command == "/next":
            show_next(chat_id)
        elif command == "/deadlines":
            show_deadlines(chat_id)
        elif command == "/goal":
            parts = text.split()
            if len(parts) > 1 and parts[1].isdigit():
                show_goal(chat_id, parts[1])
            else:
                show_board(chat_id)
        elif command == "/cancel":
            set_state(f"draft:{chat_id}", None)
            set_state(f"edit:{chat_id}", None)
            send_message(chat_id, "❌ انلغت المسودة.", main_menu())
        elif command == "/reset":
            for key in ("hist", "draft", "edit"):
                set_state(f"{key}:{chat_id}", None)
            send_message(chat_id, "🧹 انمسحت الذاكرة.", main_menu())
        else:
            handle_text(chat_id, text)
    except Exception as e:
        print(f"❌ update error: {e}")
        send_message(chat_id, f"⚠️ خطأ: <code>{esc(error_text(e))}</code>")


# ==========================================================
# 👀 MONITOR (digest, deadlines, board changes)
# ==========================================================
def broadcast(text):
    for chat_id in S["allowed_chat_ids"]:
        send_message(chat_id, text, main_menu())


def monitor_tick(force_digest=False):
    """Run from a scheduler (daily on PythonAnywhere, every few minutes standalone)."""
    board = get_board()
    now = datetime.now(LOCAL_TZ)
    today = str(now.date())

    # 1) steps checked/unchecked since the last run (web board, Claude, the bot itself...)
    snapshot = {str(s["id"]): s["done"] for g in board.get("goals", [])
                for m in g.get("missions", []) for s in m.get("steps", [])}
    old = get_state("step_snapshot")
    changes = []
    if old is not None:
        for g in board.get("goals", []):
            newly_done = False
            for m in g.get("missions", []):
                for s in m.get("steps", []):
                    was = old.get(str(s["id"]))
                    if was is not None and was != s["done"]:
                        changes.append(f"{'✅' if s['done'] else '↩️'} {esc(s['text'])} <i>({esc(g['title'])})</i>")
                        newly_done = newly_done or s["done"]
            if g["progress"]["complete"] and newly_done:
                changes.append(f"🏆 <b>{esc(g['title'])}</b> تحقق بالكامل! مبروك 🎉")
    set_state("step_snapshot", snapshot)

    # 2) deadlines (once a day per goal)
    alerted = get_state("alerted", {})
    alerts = []
    for g in board.get("goals", []):
        days = days_left(g.get("deadline", ""))
        if days is None or g["progress"]["complete"] or days > S["deadline_alert_days"]:
            continue
        if alerted.get(str(g["id"])) != today:
            alerted[str(g["id"])] = today
            alerts.append(f"{esc(g.get('emoji', '🎯'))} <b>{esc(g['title'])}</b> — {days_label(days)} · {g['progress']['pct']}%")
    set_state("alerted", alerted)

    # 3) daily digest
    digest_due = force_digest or now.hour >= S["digest_hour"]
    if digest_due and get_state("last_digest_date") != today:
        set_state("last_digest_date", today)
        items = next_steps(board)
        text = (
            f"☀️ <b>صباح الخير — ملخص Goals 2026</b>\n\n"
            f"{progress_bar(board.get('overall_pct', 0))} {board.get('overall_pct', 0)}%  ·  "
            f"🏆 {board.get('goals_achieved', 0)}/{len(board.get('goals', []))}\n"
        )
        if changes:
            text += "\n👀 <b>تغيرات من آخر مرة:</b>\n" + "\n".join(changes[:15]) + "\n"
        if alerts:
            text += "\n⏰ <b>مواعيد قريبة:</b>\n" + "\n".join(alerts) + "\n"
        text += "\n👉 <b>ركز اليوم على:</b>\n" + ("\n".join(items) if items else "كلشي مخلص! 🎉")
        broadcast(text)
        return

    if changes:
        broadcast("👀 <b>تحديثات على اللوحة</b>\n\n" + "\n".join(changes[:20]))
    if alerts:
        broadcast("⏰ <b>تنبيه مواعيد</b>\n\n" + "\n".join(alerts))


# ==========================================================
# 🌐 FLASK WEBHOOK (inside the Goals 2026 app)
# ==========================================================
def register_flask(app, tool_fn):
    """Mount POST /telegram/<secret> on the Goals 2026 Flask app."""
    global call_tool
    call_tool = tool_fn
    from flask import jsonify, request

    secret = S.get("webhook_secret", "")
    if not (S.get("bot_token") and secret):
        print("[goals_agent] bot_token / webhook_secret missing — telegram webhook disabled")
        return

    @app.post(f"/telegram/{secret}")
    def goals_agent_webhook():
        if request.headers.get("X-Telegram-Bot-Api-Secret-Token", "") != secret:
            return jsonify(ok=False), 403
        update = request.get_json(silent=True) or {}
        try:
            process_update(update)
        except Exception as e:
            print(f"❌ webhook error: {e}")
        return jsonify(ok=True)

    @app.get(f"/telegram/{secret}/health")
    def goals_agent_health():
        result = {"bot": False, "groq": False, "board": False}
        try:
            result["bot"] = tg("getMe").get("result", {}).get("username", False)
        except Exception as e:
            result["bot_error"] = str(e)
        try:
            r = requests.get("https://api.groq.com/openai/v1/models",
                             headers={"Authorization": f"Bearer {S.get('groq_api_key', '')}"}, timeout=20)
            result["groq"] = r.status_code == 200
            if r.status_code != 200:
                result["groq_error"] = f"{r.status_code} {r.text[:200]}"
        except Exception as e:
            result["groq_error"] = str(e)
        try:
            result["board"] = f"{get_board().get('overall_pct', 0)}%"
        except Exception as e:
            result["board_error"] = error_text(e)
        return jsonify(result)
