# ==========================================================
# 🎯 Goals 2026 — standalone runner (polling + Gradio dashboard)
# ----------------------------------------------------------
# Use this when the bot runs outside the Goals 2026 site
# (your PC, a server, a HuggingFace Space). It talks to the
# board through the Goals 2026 MCP server over HTTP.
# The PythonAnywhere deployment does NOT use this file: there
# goals_agent.py is mounted inside the Goals 2026 Flask app.
# ==========================================================

import json
import threading
import time
import os
from datetime import datetime

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import goals_agent as agent


# ==========================================================
# 🔐 ENV VARIABLES (never hardcode secrets)
# ==========================================================
GOALS_MCP_URL = os.environ.get("GOALS_MCP_URL", "https://Goals2026.pythonanywhere.com/mcp")
GOALS_MCP_TOKEN = os.environ.get("GOALS_MCP_TOKEN", "")
MONITOR_INTERVAL_MIN = int(os.environ.get("MONITOR_INTERVAL_MIN", "15"))

started_at = datetime.now()
status = {"mcp": "not connected", "board_pct": "—"}


# ==========================================================
# 🔌 GOALS 2026 MCP CLIENT (Streamable HTTP, JSON-RPC)
# ==========================================================
mcp_lock = threading.Lock()
mcp_session = {"ready": False, "id": None, "next_id": 1}


def _mcp_post(method, params=None, notify=False):
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if GOALS_MCP_TOKEN:
        headers["Authorization"] = f"Bearer {GOALS_MCP_TOKEN}"
    if mcp_session["id"]:
        headers["Mcp-Session-Id"] = mcp_session["id"]

    payload = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        payload["params"] = params
    request_id = None
    if not notify:
        request_id = mcp_session["next_id"]
        mcp_session["next_id"] += 1
        payload["id"] = request_id

    r = requests.post(GOALS_MCP_URL, headers=headers, json=payload, timeout=60)
    if r.headers.get("Mcp-Session-Id"):
        mcp_session["id"] = r.headers["Mcp-Session-Id"]
    r.raise_for_status()
    if notify:
        return None

    # the reply may be plain JSON or a server-sent event stream
    msg = None
    if "text/event-stream" in r.headers.get("Content-Type", ""):
        for line in r.text.splitlines():
            if line.startswith("data:"):
                try:
                    candidate = json.loads(line[5:].strip())
                except Exception:
                    continue
                if candidate.get("id") == request_id:
                    msg = candidate
                    break
        if msg is None:
            raise RuntimeError("MCP: no reply found in event stream")
    else:
        msg = r.json()
    if "error" in msg:
        raise RuntimeError(f"MCP error: {msg['error'].get('message', msg['error'])}")
    return msg.get("result", {})


def _mcp_connect():
    mcp_session.update(ready=False, id=None)
    _mcp_post("initialize", {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "goals-2026-monitor-agent", "version": "1.0"},
    })
    _mcp_post("notifications/initialized", notify=True)
    mcp_session["ready"] = True
    status["mcp"] = "connected ✅"


def mcp_call(tool, arguments=None):
    """Call a Goals 2026 tool and return its parsed JSON result."""
    with mcp_lock:
        try:
            if not mcp_session["ready"]:
                _mcp_connect()
            result = _mcp_post("tools/call", {"name": tool, "arguments": arguments or {}})
        except Exception:
            # session expired or connection dropped: reconnect once and retry
            try:
                _mcp_connect()
                result = _mcp_post("tools/call", {"name": tool, "arguments": arguments or {}})
            except Exception as e:
                status["mcp"] = f"error ❌ {e}"
                raise

    text = "".join(p.get("text", "") for p in result.get("content", []) if p.get("type") == "text")
    if result.get("isError"):
        raise RuntimeError(text or f"{tool} failed")
    if result.get("structuredContent") is not None:
        data = result["structuredContent"]
    else:
        data = json.loads(text)
    if tool == "get_board":
        status["board_pct"] = f"{data.get('overall_pct', 0)}%"
    return data


agent.call_tool = mcp_call


# ==========================================================
# 🔁 BOT LOOP (long polling) + MONITOR
# ==========================================================
def get_updates(offset=None):
    try:
        params = {"timeout": 30, "allowed_updates": json.dumps(["message", "callback_query"])}
        if offset:
            params["offset"] = offset
        r = requests.get(f"{agent.TELEGRAM_API}/getUpdates", params=params, timeout=40)
        return r.json().get("result", [])
    except Exception as e:
        print(f"❌ get_updates error: {e}")
        time.sleep(3)
        return []


def run_bot():
    if not agent.S.get("bot_token"):
        print("❌ BOT_TOKEN is missing")
        return
    agent.tg("deleteWebhook")  # polling and a webhook can't both be active
    print("🤖 Goals 2026 agent is running...")
    offset = None
    while True:
        for update in get_updates(offset):
            offset = update["update_id"] + 1
            try:
                agent.process_update(update)
            except Exception as e:
                print(f"❌ update error: {e}")


def run_monitor():
    print("👀 Monitor started")
    while True:
        try:
            if agent.S["allowed_chat_ids"]:
                agent.monitor_tick()
        except Exception as e:
            print(f"❌ monitor error: {e}")
        time.sleep(MONITOR_INTERVAL_MIN * 60)


# ==========================================================
# 📈 GRADIO DASHBOARD
# ==========================================================
def dashboard_text():
    uptime = datetime.now() - started_at
    hours, rem = divmod(int(uptime.total_seconds()), 3600)
    st = agent.stats
    return (
        "## 🎯 Goals 2026 — Monitor Agent\n\n"
        f"| | |\n|---|---|\n"
        f"| 🟢 Status | {'running' if agent.S.get('bot_token') else 'BOT_TOKEN missing'} |\n"
        f"| 🔌 Goals MCP | {status['mcp']} |\n"
        f"| 📊 Board progress | {status['board_pct']} |\n"
        f"| 💬 Messages | {st['messages']} |\n"
        f"| 📝 Plans drafted / applied | {st['plans_drafted']} / {st['plans_applied']} |\n"
        f"| 🕐 Last message | {st['last_message']} |\n"
        f"| ⚙️ Last action | {st['last_action']} |\n"
        f"| ⏱ Uptime | {hours}h {rem // 60}m |\n"
    )


# ==========================================================
# ▶️ MAIN
# ==========================================================
if __name__ == "__main__":
    import gradio as gr

    for name in ("bot_token", "groq_api_key"):
        if not agent.S.get(name):
            print(f"⚠️ {name.upper()} is not set")
    if not GOALS_MCP_TOKEN:
        print("⚠️ GOALS_MCP_TOKEN is not set — board edits will be refused")
    if not agent.S["allowed_chat_ids"]:
        print("⚠️ ALLOWED_CHAT_IDS is empty — message the bot once to see your chat id")

    threading.Thread(target=run_bot, daemon=True).start()
    threading.Thread(target=run_monitor, daemon=True).start()

    with gr.Blocks(title="Goals 2026 Agent") as demo:
        panel = gr.Markdown(dashboard_text())
        gr.Button("🔄 Refresh").click(fn=dashboard_text, outputs=panel)
    demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", "7860")))
