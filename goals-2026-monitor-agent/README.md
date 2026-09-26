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

## Setup

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
| `GOALS_MCP_URL` | Goals 2026 MCP endpoint (Streamable HTTP) |
| `GOALS_MCP_TOKEN` | Bearer token for that endpoint |
| `ALLOWED_CHAT_IDS` | Comma-separated Telegram chat ids allowed to use the bot |

The bot is private: anyone not in `ALLOWED_CHAT_IDS` gets a refusal that shows
their chat id. Use that message to find your own id.

## HuggingFace Spaces

Create a Gradio Space, upload `app.py`, `requirements.txt` and `README.md`, and add the
variables above as **Secrets**. The Gradio page shows a live status dashboard, and the
bot and monitor run in background threads using long polling (no webhook needed).
