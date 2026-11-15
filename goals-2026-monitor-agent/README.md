---
title: Goals 2026 Monitor Agent
emoji: 🎯
colorFrom: yellow
colorTo: red
sdk: gradio
python_version: 3.11
app_file: app.py
pinned: false
---

# 🎯 Goals 2026 — Telegram AI Agent + Monitor

A Telegram bot that runs all the time and manages your **Goals 2026** board
(goals → missions → steps) through the Goals 2026 MCP server, using Groq as the brain.

## How it works

1. You send any messy message: `ابي اتعلم انكليزي قبل نهاية السنة ielts 6.5 لازم اسجل بكورس`
2. Groq reads your current board and drafts a clean plan: a goal with emoji, color,
   category, deadline, "why", missions and checklist steps (or adds to an existing goal,
   or ticks steps you said you finished).
3. You get a preview with buttons:
   - ✅ **Approve**: the changes are written to Goals 2026
   - ✏️ **Edit**: send a correction ("make the deadline end of November, color teal") and it redrafts
   - ❌ **Cancel**: nothing changes
4. The bot reports the result and the new overall progress.

Questions like `شكد باقي على الماستر؟` get a plain answer, with no changes to the board.

## Monitor (background)

- ☀️ **Daily digest** at `DIGEST_HOUR`: overall progress plus the next step for each goal
- ⏰ **Deadline alerts** for goals due within `DEADLINE_ALERT_DAYS` (or overdue), once a day
- 👀 **Change watch**: tells you when steps get checked or unchecked on the board from
  elsewhere (web app, Claude, ...) and when a goal is fully achieved 🏆

## Commands and buttons

`/start` `/board` `/next` `/deadlines` `/goal <id>` `/cancel` `/reset` `/help`

On the board, tap a goal to see its missions, then tap an open step to tick it.

## Files

| File | What |
|---|---|
| `goals_agent.py` | The agent: Groq planner, Telegram handlers, approve/edit flow, monitor. Works as a webhook or with polling |
| `app.py` | Standalone runner: polling + Gradio dashboard, reaches the board through the Goals 2026 MCP server |
| `pythonanywhere/app_hook.py` | Lines appended to the Goals 2026 `app.py` to mount the webhook |
| `pythonanywhere/goals_agent_daily.py` | Daily scheduled task: digest, deadline alerts, changes since yesterday |

## Deploy inside the Goals 2026 site (PythonAnywhere, recommended)

The bot runs as a webhook inside `Goals2026.pythonanywhere.com` and edits the board directly,
so no MCP token is needed and it works on a free account.

1. Upload `goals_agent.py` and `pythonanywhere/goals_agent_daily.py` to `/home/Goals2026/goals2026/`.
2. Create `/home/Goals2026/goals2026/goals_agent.json` from `pythonanywhere/goals_agent.example.json`.
3. Paste `pythonanywhere/app_hook.py` into `/home/Goals2026/goals2026/app.py`, just above
   `if __name__ == "__main__":`, then reload the web app.
4. Check `https://Goals2026.pythonanywhere.com/telegram/<webhook_secret>/health`. It should show
   `"bot"`, `"groq": true` and the board percentage.
5. Point the bot at it:
   `https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://Goals2026.pythonanywhere.com/telegram/<webhook_secret>&secret_token=<webhook_secret>&drop_pending_updates=true`
6. Add a daily scheduled task at 06:00 UTC (09:00 Iraq):
   `python3.10 /home/Goals2026/goals2026/goals_agent_daily.py`

To undo: restore `app.py.bak-2026-09-26`, reload the web app, and call `deleteWebhook`.

## Run standalone (PC / server / HuggingFace Space)


```bash
pip install -r requirements.txt
cp .env.example .env   # fill in your values
python app.py
```

| Variable | What |
|---|---|
| `BOT_TOKEN` | From @BotFather |
| `GROQ_API_KEY` | From console.groq.com |
| `GROQ_MODEL` | Default `openai/gpt-oss-120b` |
| `GOALS_MCP_URL` | Default `https://Goals2026.pythonanywhere.com/mcp` |
| `GOALS_MCP_TOKEN` | Bearer token for that endpoint |
| `ALLOWED_CHAT_IDS` | Comma-separated Telegram chat ids allowed to use the bot |

The bot is private: anyone not in `ALLOWED_CHAT_IDS` gets a refusal that shows
their chat id. Use that message to find your own id.

## HuggingFace Spaces

Create a Gradio Space, upload `app.py`, `requirements.txt` and `README.md`, and add the
variables above as **Secrets**. The Gradio page shows a live status dashboard, and the
bot and monitor run in background threads using long polling (no webhook needed).
