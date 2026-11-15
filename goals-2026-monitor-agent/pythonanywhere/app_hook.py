

# ---------- Telegram agent (goals_agent.py, settings in goals_agent.json) ----------
try:
    sys.path.insert(0, BASE)
    import goals_agent

    def _agent_tool(name, args):
        try:
            return run_tool(name, args)
        except Exception:
            db().rollback()
            raise

    goals_agent.register_flask(app, _agent_tool)
except Exception as _agent_error:
    print(f"[goals] telegram agent disabled: {_agent_error}")
