# ==========================================================
# 🎯 Goals 2026 — Telegram AI Agent + Monitor
# ----------------------------------------------------------
# Send the bot any messy message ("rubbish" notes, voice-to-text,
# half ideas...). Groq turns it into a clean plan for your
# Goals 2026 board (goals → missions → steps, with emoji, color,
# category, deadline). You get a preview and choose:
#   ✅ Approve  →  the plan is written to Goals 2026 via its MCP server
#   ✏️ Edit     →  send a correction, the plan is redrafted
#   ❌ Cancel   →  nothing is written
# A background monitor sends a daily digest, deadline alerts and
# tells you when steps get checked on the board from elsewhere.
# ==========================================================

import json
import gradio as gr
import threading
import requests
import time
import os
import html
from datetime import datetime, timedelta, timezone

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


# ==========================================================
# 🔐 ENV VARIABLES (never hardcode secrets)
# ==========================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

GOALS_MCP_URL = os.environ.get("GOALS_MCP_URL", "")        # Streamable HTTP MCP endpoint
GOALS_MCP_TOKEN = os.environ.get("GOALS_MCP_TOKEN", "")    # Bearer token for the MCP server

# Only these Telegram chat ids can use the bot (comma separated)
ALLOWED_CHAT_IDS = [
    int(x) for x in os.environ.get("ALLOWED_CHAT_IDS", "").replace(" ", "").split(",") if x
]

TZ_OFFSET_HOURS = float(os.environ.get("TZ_OFFSET_HOURS", "3"))       # Iraq = UTC+3
DIGEST_HOUR = int(os.environ.get("DIGEST_HOUR", "9"))                 # daily digest local hour
MONITOR_INTERVAL_MIN = int(os.environ.get("MONITOR_INTERVAL_MIN", "15"))
DEADLINE_ALERT_DAYS = int(os.environ.get("DEADLINE_ALERT_DAYS", "3"))

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
LOCAL_TZ = timezone(timedelta(hours=TZ_OFFSET_HOURS))


# ==========================================================
# 📊 BOT STATE (dictionary-based)
# ==========================================================
stats = {
    "started_at": datetime.now(),
    "messages": 0,
    "users": set(),
    "plans_drafted": 0,
    "plans_applied": 0,
    "last_message": "—",
    "last_action": "—",
    "mcp_status": "not connected",
    "board_pct": "—",
}

drafts = {}               # chat_id -> {"source": str, "reply": str, "actions": [...]}
awaiting_edit = set()     # chat_ids whose next text message is an edit to the draft
conversation_history = {} # chat_id -> short memory for Q&A
MAX_HISTORY = 10

monitor_state = {
    "last_digest_date": None,
    "alerted": {},        # goal_id -> date string of last deadline alert
    "step_snapshot": None # step_id -> done
}


# ==========================================================
# 🔌 GOALS 2026 MCP CLIENT (Streamable HTTP, JSON-RPC)
# ==========================================================
mcp_lock = threading.Lock()
step_names = {}  # step_id -> text, refreshed on every get_board()
mcp_session = {"id": None, "next_id": 1}


def _mcp_headers():
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if GOALS_MCP_TOKEN:
        headers["Authorization"] = f"Bearer {GOALS_MCP_TOKEN}"
    if mcp_session["id"]:
        headers["Mcp-Session-Id"] = mcp_session["id"]
    return headers


def _mcp_parse(response, request_id):
    """Read a JSON-RPC reply that may come back as plain JSON or as SSE."""
    content_type = response.headers.get("Content-Type", "")
    if "text/event-stream" in content_type:
        for line in response.text.splitlines():
            if line.startswith("data:"):
                try:
                    msg = json.loads(line[5:].strip())
                except Exception:
                    continue
                if msg.get("id") == request_id:
                    return msg
        raise RuntimeError("MCP: no reply found in event stream")
    return response.json()


def _mcp_post(method, params=None, notify=False):
    payload = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        payload["params"] = params
    request_id = None
    if not notify:
        request_id = mcp_session["next_id"]
        mcp_session["next_id"] += 1
        payload["id"] = request_id

    r = requests.post(GOALS_MCP_URL, headers=_mcp_headers(), json=payload, timeout=60)
    if r.headers.get("Mcp-Session-Id"):
        mcp_session["id"] = r.headers["Mcp-Session-Id"]
    if r.status_code == 404 and mcp_session["id"]:
        raise ConnectionResetError("MCP session expired")
    r.raise_for_status()
    if notify:
        return None
    msg = _mcp_parse(r, request_id)
    if "error" in msg:
        raise RuntimeError(f"MCP error: {msg['error'].get('message', msg['error'])}")
    return msg.get("result", {})


def _mcp_connect():
    mcp_session["id"] = None
    _mcp_post("initialize", {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "goals-2026-monitor-agent", "version": "1.0"},
    })
    _mcp_post("notifications/initialized", notify=True)
    stats["mcp_status"] = "connected ✅"


def mcp_call(tool, arguments=None):
    """Call a Goals 2026 tool and return its parsed JSON result."""
    if not GOALS_MCP_URL:
        raise RuntimeError("GOALS_MCP_URL is not set")
    with mcp_lock:
        try:
            if not mcp_session["id"]:
                _mcp_connect()
            result = _mcp_post("tools/call", {"name": tool, "arguments": arguments or {}})
        except Exception:
            # session expired or connection dropped: reconnect once and retry
            try:
                _mcp_connect()
                result = _mcp_post("tools/call", {"name": tool, "arguments": arguments or {}})
            except Exception as e:
                stats["mcp_status"] = f"error ❌ {e}"
                raise

    text = ""
    for part in result.get("content", []):
        if part.get("type") == "text":
            text += part.get("text", "")
    if result.get("isError"):
        raise RuntimeError(text or f"{tool} failed")
    if result.get("structuredContent") is not None:
        return result["structuredContent"]
    try:
        return json.loads(text)
    except Exception:
        return text


def get_board():
    board = mcp_call("get_board")
    if isinstance(board, dict):
        stats["board_pct"] = f"{board.get('overall_pct', 0)}%"
        for g in board.get("goals", []):
            for m in g.get("missions", []):
                for s in m.get("steps", []):
                    step_names[s["id"]] = s["text"]
    return board


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
        tool = a.get("tool")
        if tool not in TOOL_ARGS:
            continue
        args = {k: v for k, v in (a.get("args") or {}).items() if k in TOOL_ARGS[tool]}
        if args.get("color") and args["color"] not in COLORS:
            args.pop("color")
        cleaned.append({"tool": tool, "args": args, "summary": str(a.get("summary", ""))[:300]})
    return cleaned


# ==========================================================
# 🧠 GROQ PLANNER
# ==========================================================
def compact_board(board):
    """Small text version of the board so the prompt stays short."""
    if not isinstance(board, dict):
        return "(board unavailable)"
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
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    body = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 2048,
        "response_format": {"type": "json_object"},
    }
    r = requests.post(GROQ_URL, headers=headers, json=body, timeout=60)
    r.raise_for_status()
    return json.loads(r.json()["choices"][0]["message"]["content"])


def draft_plan(chat_id, user_message, current_draft=None):
    board = get_board()
    today = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d (%A)")
    messages = [{"role": "system", "content": PLANNER_PROMPT.format(today=today, board=compact_board(board))}]
    messages += conversation_history.get(chat_id, [])[-MAX_HISTORY:]
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

    history = conversation_history.setdefault(chat_id, [])
    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": reply})
    conversation_history[chat_id] = history[-MAX_HISTORY:]
    return reply, actions, board


# ==========================================================
# 🖼️ FORMATTING (Telegram HTML)
# ==========================================================
def esc(text):
    return html.escape(str(text or ""))


def progress_bar(pct, width=10):
    filled = int(round((pct or 0) / 100 * width))
    return "▰" * filled + "▱" * (width - filled)


def format_action(action):
    tool, args = action["tool"], action["args"]
    if tool == "create_goal":
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

    icon = "⚠️ " if tool in DANGEROUS_TOOLS else "✏️ "
    text = f"{icon}<b>{esc(tool)}</b> — {esc(action.get('summary') or '')}"
    if tool == "add_mission":
        for s in args.get("steps") or []:
            text += f"\n      ☐ {esc(s)}"
    if tool == "add_steps":
        for s in args.get("steps") or []:
            text += f"\n      ☐ {esc(s)}"
    if tool == "check_steps":
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


def next_steps(board, limit=5):
    """First unchecked step of each goal — the 'do this next' list."""
    items = []
    for g in board.get("goals", []):
        for m in g.get("missions", []):
            open_steps = [s for s in m.get("steps", []) if not s["done"]]
            if open_steps:
                items.append(f"{g.get('emoji', '🎯')} {esc(open_steps[0]['text'])}  <i>({esc(g['title'])})</i>")
                break
    return items[:limit]


# ==========================================================
# 📨 TELEGRAM FUNCTIONS
# ==========================================================
def send_message(chat_id, text, reply_markup=None):
    try:
        payload = {
            "chat_id": chat_id,
            "text": text[:4000],
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        r = requests.post(f"{TELEGRAM_API}/sendMessage", data=payload, timeout=30)
        return r.json()
    except Exception as e:
        print(f"❌ send_message error: {e}")


def edit_message(chat_id, message_id, text, reply_markup=None):
    try:
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text[:4000],
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        requests.post(f"{TELEGRAM_API}/editMessageText", data=payload, timeout=30)
    except Exception as e:
        print(f"❌ edit_message error: {e}")


def send_typing(chat_id):
    try:
        requests.post(f"{TELEGRAM_API}/sendChatAction", data={"chat_id": chat_id, "action": "typing"}, timeout=10)
    except Exception:
        pass


def answer_callback(callback_id, text=""):
    try:
        requests.post(f"{TELEGRAM_API}/answerCallbackQuery",
                      data={"callback_query_id": callback_id, "text": text}, timeout=10)
    except Exception:
        pass


def get_updates(offset=None):
    try:
        params = {"timeout": 30, "allowed_updates": json.dumps(["message", "callback_query"])}
        if offset:
            params["offset"] = offset
        r = requests.get(f"{TELEGRAM_API}/getUpdates", params=params, timeout=40)
        return r.json().get("result", [])
    except Exception as e:
        print(f"❌ get_updates error: {e}")
        time.sleep(3)
        return []


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
    "/board — اللوحة\n/next — الخطوات التالية\n/goal 3 — تفاصيل هدف\n"
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
    g = mcp_call("get_goal", {"goal_id": int(goal_id)})
    g = g.get("goal", g) if isinstance(g, dict) else g
    if message_id:
        edit_message(chat_id, message_id, format_goal(g), goal_menu(g))
    else:
        send_message(chat_id, format_goal(g), goal_menu(g))


def show_next(chat_id):
    board = get_board()
    items = next_steps(board)
    text = "👉 <b>الخطوات التالية / Next steps</b>\n\n" + ("\n".join(items) if items else "كلشي مخلص! 🎉")
    send_message(chat_id, text, main_menu())


def show_deadlines(chat_id):
    board = get_board()
    today = datetime.now(LOCAL_TZ).date()
    rows = []
    for g in board.get("goals", []):
        if g.get("deadline") and not g["progress"]["complete"]:
            try:
                days = (datetime.strptime(g["deadline"], "%Y-%m-%d").date() - today).days
            except Exception:
                continue
            rows.append((days, f"{g.get('emoji', '🎯')} <b>{esc(g['title'])}</b> — {g['deadline']} "
                               f"({'متأخر ' + str(-days) + ' يوم' if days < 0 else 'باقي ' + str(days) + ' يوم'}) "
                               f"· {g['progress']['pct']}%"))
    rows.sort()
    text = "⏰ <b>المواعيد / Deadlines</b>\n\n" + ("\n".join(r[1] for r in rows) if rows else "ماكو مواعيد محددة.")
    send_message(chat_id, text, main_menu())


def apply_draft(chat_id):
    draft = drafts.pop(chat_id, None)
    awaiting_edit.discard(chat_id)
    if not draft or not draft["actions"]:
        send_message(chat_id, "ماكو مسودة حالياً 🤷")
        return
    results = []
    for a in draft["actions"]:
        try:
            mcp_call(a["tool"], a["args"])
            label = a["args"].get("title") or a.get("summary") or a["tool"]
            results.append(f"✅ {esc(a['tool'])}: {esc(label)}")
        except Exception as e:
            results.append(f"❌ {esc(a['tool'])}: {esc(e)}")
    stats["plans_applied"] += 1
    stats["last_action"] = f"{datetime.now():%H:%M} applied {len(draft['actions'])} change(s)"
    board = get_board()
    remember_snapshot(board)
    text = "🎉 <b>تم التنفيذ / Done</b>\n\n" + "\n".join(results)
    text += f"\n\n📊 التقدم الكلي: {progress_bar(board.get('overall_pct', 0))} {board.get('overall_pct', 0)}%"
    send_message(chat_id, text, main_menu())


def handle_text(chat_id, text):
    send_typing(chat_id)
    current = drafts.get(chat_id) if chat_id in awaiting_edit else None
    awaiting_edit.discard(chat_id)
    try:
        reply, actions, _ = draft_plan(chat_id, text, current)
    except Exception as e:
        print(f"❌ planner error: {e}")
        send_message(chat_id, f"⚠️ صار خطأ: <code>{esc(e)}</code>\nجرب مرة ثانية.")
        return

    if not actions:
        send_message(chat_id, esc(reply) or "👍", main_menu())
        return

    drafts[chat_id] = {"source": current["source"] if current else text, "reply": reply, "actions": actions}
    stats["plans_drafted"] += 1
    send_message(chat_id, format_draft(drafts[chat_id]), draft_menu())


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
            edit_message(chat_id, message_id, callback["message"].get("text", "")[:3900] + "\n\n⏳ جاري التنفيذ...")
            apply_draft(chat_id)
        elif data == "edit":
            answer_callback(callback_id)
            if chat_id not in drafts:
                send_message(chat_id, "ماكو مسودة حالياً 🤷")
                return
            awaiting_edit.add(chat_id)
            send_message(chat_id, "✏️ اكتب شنو تريد أغير (مثلاً: <i>خلي الموعد نهاية نوفمبر وضيف خطوة مراجعة</i>)")
        elif data == "cancel":
            drafts.pop(chat_id, None)
            awaiting_edit.discard(chat_id)
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
            mcp_call("check_steps", {"step_ids": [int(step_id)], "done": True})
            answer_callback(callback_id, "✅")
            stats["last_action"] = f"{datetime.now():%H:%M} checked step #{step_id}"
            remember_snapshot(get_board())
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
        send_message(chat_id, f"⚠️ خطأ: <code>{esc(e)}</code>")


# ==========================================================
# 🔒 ACCESS
# ==========================================================
def is_allowed(chat_id):
    return chat_id in ALLOWED_CHAT_IDS


# ==========================================================
# 👀 MONITOR (digest, deadlines, external changes)
# ==========================================================
def remember_snapshot(board):
    snap = {}
    for g in board.get("goals", []):
        for m in g.get("missions", []):
            for s in m.get("steps", []):
                snap[s["id"]] = (s["done"], s["text"], g.get("emoji", "🎯"))
    monitor_state["step_snapshot"] = snap


def broadcast(text):
    for chat_id in ALLOWED_CHAT_IDS:
        send_message(chat_id, text, main_menu())


def monitor_tick():
    board = get_board()
    now = datetime.now(LOCAL_TZ)
    today = now.date()

    # 1) steps checked/unchecked from elsewhere (web board, Claude, ...)
    old = monitor_state["step_snapshot"]
    if old is not None:
        changes = []
        for g in board.get("goals", []):
            for m in g.get("missions", []):
                for s in m.get("steps", []):
                    if s["id"] in old and old[s["id"]][0] != s["done"]:
                        changes.append(f"{'✅' if s['done'] else '↩️'} {esc(s['text'])} <i>({esc(g['title'])})</i>")
            if g["progress"]["complete"] and any(
                s["id"] in old and not old[s["id"]][0]
                for m in g.get("missions", []) for s in m.get("steps", [])
            ):
                changes.append(f"🏆 <b>{esc(g['title'])}</b> تحقق بالكامل! مبروك 🎉")
        if changes:
            broadcast("👀 <b>تحديثات على اللوحة</b>\n\n" + "\n".join(changes[:20]))
    remember_snapshot(board)

    # 2) deadline alerts (once a day per goal)
    alerts = []
    for g in board.get("goals", []):
        if not g.get("deadline") or g["progress"]["complete"]:
            continue
        try:
            days = (datetime.strptime(g["deadline"], "%Y-%m-%d").date() - today).days
        except Exception:
            continue
        if days <= DEADLINE_ALERT_DAYS and monitor_state["alerted"].get(g["id"]) != str(today):
            monitor_state["alerted"][g["id"]] = str(today)
            when = f"متأخر {-days} يوم" if days < 0 else ("اليوم!" if days == 0 else f"باقي {days} يوم")
            alerts.append(f"{g.get('emoji', '🎯')} <b>{esc(g['title'])}</b> — {when} · {g['progress']['pct']}%")
    if alerts:
        broadcast("⏰ <b>تنبيه مواعيد</b>\n\n" + "\n".join(alerts))

    # 3) daily digest
    if now.hour >= DIGEST_HOUR and monitor_state["last_digest_date"] != str(today):
        monitor_state["last_digest_date"] = str(today)
        items = next_steps(board)
        broadcast(
            f"☀️ <b>صباح الخير — ملخص Goals 2026</b>\n\n"
            f"{progress_bar(board.get('overall_pct', 0))} {board.get('overall_pct', 0)}%  ·  "
            f"🏆 {board.get('goals_achieved', 0)}/{len(board.get('goals', []))}\n\n"
            "👉 <b>ركز اليوم على:</b>\n" + ("\n".join(items) if items else "كلشي مخلص! 🎉")
        )


def run_monitor():
    print("👀 Monitor started")
    while True:
        try:
            if ALLOWED_CHAT_IDS and GOALS_MCP_URL:
                monitor_tick()
        except Exception as e:
            print(f"❌ monitor error: {e}")
        time.sleep(MONITOR_INTERVAL_MIN * 60)


# ==========================================================
# 🔁 BOT LOOP (long polling)
# ==========================================================
def run_bot():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN is missing")
        return
    print("🤖 Goals 2026 agent is running...")
    offset = None
    while True:
        try:
            for update in get_updates(offset):
                offset = update["update_id"] + 1

                if "callback_query" in update:
                    handle_callback(update["callback_query"])
                    continue

                message = update.get("message")
                if not message or "text" not in message:
                    continue

                chat_id = message["chat"]["id"]
                text = message["text"].strip()
                user_name = message.get("from", {}).get("first_name", "")

                stats["messages"] += 1
                stats["users"].add(chat_id)
                stats["last_message"] = f"{datetime.now():%H:%M} {text[:60]}"

                if not is_allowed(chat_id):
                    send_message(chat_id, "⛔ هذا البوت خاص.\n"
                                          f"Your chat id: <code>{chat_id}</code>\n"
                                          "Add it to <code>ALLOWED_CHAT_IDS</code> to get access.")
                    continue

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
                    drafts.pop(chat_id, None)
                    awaiting_edit.discard(chat_id)
                    send_message(chat_id, "❌ انلغت المسودة.", main_menu())
                elif command == "/reset":
                    conversation_history.pop(chat_id, None)
                    drafts.pop(chat_id, None)
                    awaiting_edit.discard(chat_id)
                    send_message(chat_id, "🧹 انمسحت الذاكرة.", main_menu())
                else:
                    handle_text(chat_id, text)
        except Exception as e:
            print(f"❌ bot loop error: {e}")
            time.sleep(3)


# ==========================================================
# 📈 GRADIO DASHBOARD
# ==========================================================
def dashboard_text():
    uptime = datetime.now() - stats["started_at"]
    hours, rem = divmod(int(uptime.total_seconds()), 3600)
    return (
        "## 🎯 Goals 2026 — Monitor Agent\n\n"
        f"| | |\n|---|---|\n"
        f"| 🟢 Status | {'running' if BOT_TOKEN else 'BOT_TOKEN missing'} |\n"
        f"| 🔌 Goals MCP | {stats['mcp_status']} |\n"
        f"| 📊 Board progress | {stats['board_pct']} |\n"
        f"| 💬 Messages | {stats['messages']} |\n"
        f"| 👥 Users | {len(stats['users'])} |\n"
        f"| 📝 Plans drafted / applied | {stats['plans_drafted']} / {stats['plans_applied']} |\n"
        f"| 🕐 Last message | {stats['last_message']} |\n"
        f"| ⚙️ Last action | {stats['last_action']} |\n"
        f"| ⏱ Uptime | {hours}h {rem // 60}m |\n"
    )


with gr.Blocks(title="Goals 2026 Agent") as demo:
    panel = gr.Markdown(dashboard_text())
    gr.Button("🔄 Refresh").click(fn=dashboard_text, outputs=panel)


# ==========================================================
# ▶️ MAIN
# ==========================================================
if __name__ == "__main__":
    for name, value in [("BOT_TOKEN", BOT_TOKEN), ("GROQ_API_KEY", GROQ_API_KEY), ("GOALS_MCP_URL", GOALS_MCP_URL)]:
        if not value:
            print(f"⚠️ {name} is not set")
    if not ALLOWED_CHAT_IDS:
        print("⚠️ ALLOWED_CHAT_IDS is empty — message the bot once to see your chat id")

    threading.Thread(target=run_bot, daemon=True).start()
    threading.Thread(target=run_monitor, daemon=True).start()

    demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", "7860")))
