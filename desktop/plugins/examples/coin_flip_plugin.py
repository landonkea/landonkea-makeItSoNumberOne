# ───────────────────────────────────────────────────────────────────
# coin_flip_plugin.py — TEMPLATE third-party plugin
# ───────────────────────────────────────────────────────────────────
# This is a worked example of a third-party action plugin, not
# something that's active out of the box. To try it out:
#
#   cp desktop/plugins/examples/coin_flip_plugin.py desktop/plugins/
#
# (desktop/plugins/*.py is gitignored — see .gitignore — everything
# EXCEPT this examples/ folder, which is the documented template).
# The next time the assistant starts, you'll see a startup log line
# like:
#
#   [plugins] Loaded plugin "flip_coin" from coin_flip_plugin.py (FlipCoinPlugin)
#
# and Claude can now use a `flip_coin` action, e.g. you could say
# "Computer, flip a coin" and (assuming the system prompt or a
# routines.yaml entry produces a flip_coin action) get back "Heads!"
# or "Tails!".
#
# Only desktop/plugins/*.py (directly inside that folder, not
# subdirectories — this examples/ folder is intentionally NOT
# scanned) is auto-discovered at startup. See core/plugin_loader.py
# for the discovery mechanics and README.md's "Writing a plugin"
# section for the full walkthrough.
# ───────────────────────────────────────────────────────────────────

import random

# This relative import works because desktop/ is on sys.path (both
# make_it_so.py and text_mode.py add it before importing anything
# from core/), the same way core/action_router.py itself imports
# plugin_base.
from core.plugin_base import ActionPlugin


class FlipCoinPlugin(ActionPlugin):
    # The action name Claude's ACTIONS block (or a routines.yaml
    # entry) uses to invoke this plugin, e.g.:
    #   - action: flip_coin
    #     params: {}
    action_name = "flip_coin"

    # Optional, but good practice: a one-line description and a
    # param schema. Nothing in the loader enforces these — they're
    # documentation for humans (and a natural place for a future
    # "list available actions" feature to read from).
    description = "Flip a coin and report heads or tails."
    param_schema = {}  # takes no parameters

    def execute(self, params: dict, config: dict) -> str:
        # `params` is this action's parameters (empty here — this
        # plugin doesn't need any). `config` is the app's full
        # config.yaml contents, in case a plugin needs API keys or
        # settings — this one doesn't use it.
        #
        # IMPORTANT: return a message, don't raise, for any
        # foreseeable error condition. This action can't really
        # fail, but see actions/integrations.py's get_weather() for
        # the pattern a plugin that talks to a network/API should
        # follow (check what it needs up front, return a clear
        # string explaining what's missing/wrong instead of letting
        # an exception escape).
        result = random.choice(["Heads", "Tails"])
        return f"{result}!"
