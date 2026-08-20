# ───────────────────────────────────────────────────────────────────
# enroll_voice_plugin.py, teach the assistant your voice
# ───────────────────────────────────────────────────────────────────
# Say "Computer, enroll my voice as Landon" and it records a few
# seconds after the chime, the same way any other command does, then
# saves a voice fingerprint under that name (see core/voice_id.py for
# how, and its real limits -- pitch/loudness/timbre DSP, not a neural
# embedding model). Once at least one name is enrolled,
# make_it_so.py's main loop tries to identify who's speaking on every
# turn and makes that available to other plugins (currently
# journal_entry_plugin.py, see its own docstring) via
# config["_identified_speaker"].
#
# To try it out:
#
#   cp desktop/plugins/examples/enroll_voice_plugin.py desktop/plugins/
#
# (desktop/plugins/*.py is gitignored -- see .gitignore -- everything
# EXCEPT this examples/ folder, which is the documented template.)
#
# For Claude to actually emit an enroll_voice action when you say
# "Computer, enroll my voice as ...", this also needs to be documented
# in core/ai.py's _JSON_FORMAT_ADDENDUM -- see that file.
#
# One real limitation worth stating plainly: this records ONE short
# sample per enrollment. A voice fingerprint built from a single ~3
# second clip is noisier than one averaged over several recordings —
# fine for telling a small household's clearly-different voices apart
# in practice, not something to rely on on for anything security-
# sensitive.
# ───────────────────────────────────────────────────────────────────

from core.plugin_base import ActionPlugin


class EnrollVoicePlugin(ActionPlugin):
    action_name = "enroll_voice"
    description = "Record a short voice sample and save it as a named voice profile."
    param_schema = {"name": "str, whose voice this is, e.g. \"Landon\""}

    def execute(self, params: dict, config: dict) -> str:
        name = (params.get("name") or "").strip()
        if not name:
            return "No name was given -- say who this voice belongs to, e.g. \"enroll my voice as Landon\"."

        from core import audio, voice_id

        print(f"  [enroll_voice] Recording a sample for \"{name}\"...")
        audio_data = audio.record_until_silence(timeout_seconds=10)
        if audio_data is None:
            return "Didn't hear anything -- try again and speak for a few seconds after the chime."

        if voice_id.enroll(name, audio_data):
            return f"Got it -- I'll recognize {name}'s voice from now on."
        return "That recording was too quiet or too short to use -- try again a bit closer to the mic."
