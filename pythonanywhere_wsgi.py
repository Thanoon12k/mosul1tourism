"""WSGI entry point for the harith1mosul1tourist PythonAnywhere account."""

import sys

PROJECT_HOME = "/home/harith1mosul1tourist/harthwebsite"
if PROJECT_HOME not in sys.path:
    sys.path.insert(0, PROJECT_HOME)

from app import app as application  # noqa: E402
