#!/usr/bin/env sh
# ───────────────────────────────────────────────────────────────────
# docker-entrypoint.sh, generate config.yaml from env vars, if needed
# ───────────────────────────────────────────────────────────────────
# make_it_so.load_config() (reused by text_mode.py) only knows how to
# read desktop/config.yaml off disk, it has no concept of
# environment variables. To let docker-compose hand in API keys via
# a .env file (see docker-compose.yml + .env.example) without having
# to hand-edit a config.yaml on the host first, this entrypoint writes
# /app/desktop/config.yaml from ANTHROPIC_API_KEY / OPENAI_API_KEY /
# etc. env vars on first start, but ONLY if config.yaml isn't already
# there. If you'd rather manage config.yaml yourself, just bind-mount
# your own over /app/desktop/config.yaml (see the commented volume in
# docker-compose.yml) and this step is skipped entirely.
# ───────────────────────────────────────────────────────────────────
set -e

CONFIG_PATH="/app/desktop/config.yaml"

if [ ! -f "$CONFIG_PATH" ]; then
    python3 - "$CONFIG_PATH" <<'PY'
import os
import sys

import yaml

config_path = sys.argv[1]

config = {
    "mode": os.environ.get("MIS_MODE", "auto"),
    "anthropic_api_key": os.environ.get("ANTHROPIC_API_KEY", ""),
    "openai_api_key": os.environ.get("OPENAI_API_KEY", ""),
    "porcupine_access_key": os.environ.get("PORCUPINE_ACCESS_KEY", ""),
    "ollama_model": os.environ.get("OLLAMA_MODEL", "llama3.2"),
}

with open(config_path, "w") as f:
    yaml.safe_dump(config, f, default_flow_style=False)

print(f"  [entrypoint] Generated {config_path} from environment "
      f"variables.")
PY
fi

exec "$@"
