# ───────────────────────────────────────────────────────────────────
# desktop/Dockerfile — Make It So Number One, TEXT MODE ONLY
# ───────────────────────────────────────────────────────────────────
# WHAT THIS CONTAINER IS FOR
# ---------------------------
# The desktop assistant's normal voice loop (make_it_so.py) needs a
# real microphone and speaker — hardware a container doesn't have.
# This image instead runs text_mode.py (see desktop/text_mode.py),
# which drives the exact same brain (core/routines.py,
# core/ai.py, core/action_router.py) from stdin/stdout. That makes
# the container genuinely useful — scripted/CI smoke tests of the AI
# pipeline, exercising routines.yaml macros, headless use — instead
# of a container that just crashes looking for a mic.
#
# Full voice mode (wake word + microphone + speaker) still requires
# running make_it_so.py natively on real hardware. See README.md.
#
# BUILD CONTEXT
# --------------
# Build from the REPO ROOT (not desktop/), because ai.py loads the
# shared system prompt from <repo root>/shared/prompts/ — this image
# needs that file too:
#   docker build -f desktop/Dockerfile -t make-it-so-desktop .
# (docker-compose.yml at the repo root already does this for you.)
# ───────────────────────────────────────────────────────────────────

FROM python:3.11-slim

# pyaudio (in requirements.txt) compiles a C extension against
# PortAudio at install time — same requirement CI documents in
# .github/workflows/ci.yml. We install the system library here so the
# FULL requirements.txt (including pyaudio) installs cleanly, even
# though text_mode.py itself never imports pyaudio — every audio-
# touching module (audio.py, wake_word.py) already imports pyaudio/
# pvporcupine lazily INSIDE its functions rather than at module load
# time, so this container starts and runs text mode fine regardless;
# installing portaudio19-dev just means the image also has everything
# needed if someone extends it later, and matches CI exactly so
# "works in CI" and "works in this image" mean the same thing.
RUN apt-get update && apt-get install -y --no-install-recommends \
        portaudio19-dev \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (separate layer from app code so
# `docker build` doesn't reinstall everything on every source change).
COPY desktop/requirements.txt desktop/requirements.txt
RUN pip install --no-cache-dir -r desktop/requirements.txt

# shared/prompts/system_prompt.txt is loaded by core/ai.py — see the
# BUILD CONTEXT note above for why this has to be copied in too.
COPY shared/ shared/
COPY desktop/ desktop/

WORKDIR /app/desktop

# Generates config.yaml from ANTHROPIC_API_KEY / OPENAI_API_KEY / etc.
# environment variables (see docker-compose.yml + .env.example) if no
# config.yaml was volume-mounted in already.
COPY desktop/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python3", "text_mode.py"]
