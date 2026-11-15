"""Daily Goals 2026 digest — run as a PythonAnywhere scheduled task.

Lives next to app.py in /home/Goals2026/goals2026/ and uses the board directly:
    python3.10 /home/Goals2026/goals2026/goals_agent_daily.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from app import app, db, run_tool  # noqa: E402
import goals_agent  # noqa: E402


def tool(name, args):
    try:
        return run_tool(name, args)
    except Exception:
        db().rollback()
        raise


goals_agent.call_tool = tool

with app.app_context():
    goals_agent.monitor_tick(force_digest=True)
print("goals_agent daily digest sent")
