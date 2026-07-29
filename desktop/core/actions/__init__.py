# ───────────────────────────────────────────────────────────────────
# actions/__init__.py — imports all action modules
# ───────────────────────────────────────────────────────────────────
# This file makes the `actions` folder a Python package so we can
# do `from . import actions` and access `actions.system`, etc.
# ───────────────────────────────────────────────────────────────────

from . import system
from . import web_actions
