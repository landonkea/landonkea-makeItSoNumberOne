# Feature Ideas

Eighteen ideas for where Make It So could go next. All of them build on
architecture that already exists, the plugin system, routines.yaml macros,
profile.yaml contacts, the weather/calendar/reminders integrations, rather
than proposing a rewrite. Rough size and the file(s) each would touch are
noted so picking one up doesn't require re-deriving the codebase first.

## Voice and interaction

**1. Emergency/duress phrase.** A dedicated trigger phrase that, instead of
running through routines.yaml like a normal macro, sends a text (or places a
call) to whoever's marked as the emergency contact in `profile.yaml`, with
location if the platform can get it. Android and iOS already have
`send_sms`/`make_call` and contact-name resolution; this is mostly wiring a
new profile field (`emergency_contact:`) and one hardcoded trigger that
can't be edited by voice, on purpose.

**2. Speaker-based profile switching.** `profile.yaml` already supports
multiple people sharing one device, but you have to say "switch to Guest's
profile" by hand. A short enrolled voice sample per profile (a few seconds,
matched with something as simple as MFCC + cosine similarity, no ML training
required) could auto-select the active profile from who's actually talking.
Medium-sized, desktop-first (`core/profile.py`, `core/wake_word.py`).

**3. "What are you allowed to do right now."** A built-in action that reads
back the live security state out loud, `security.allowed_commands`, whether
a command is currently pending confirmation, what's in
`denied_read_paths`, instead of making someone go check `config.yaml`. Small,
one new `ActionPlugin` in `plugins_builtin.py` next to the existing security
gates in `actions/system.py`.

**4. Scheduled do-not-disturb.** `sleep_mode` today takes a duration and
that's it. Recurring windows ("every weeknight, 10pm to 7am") would turn it
into an actual DND schedule instead of a one-shot command you have to repeat
nightly. Fits naturally as a `routines.yaml` extension plus a small
scheduler loop in `core/routines.py`.

**5. Multi-action chaining from one sentence.** JSON action lists already
let Claude return several actions per turn; routines.yaml macros are still
one trigger to one canned list. Letting a spoken command reference two
routines at once ("good morning, then leaving for work") would let people
compose macros on the fly instead of pre-writing every combination.

## Star Trek theming

**6. "Red alert" scene macro.** A themed routine bundling several actions,
mute notifications, `sleep_mode`, close specific apps, behind one phrase.
Doesn't need new code, just a well-written `routines.example.yaml` entry
that shows off what multi-action macros can already do, plus maybe a
distinct alert-tone chime alongside `computer_chime.wav`.

**7. Alternate wake phrases per profile.** Porcupine supports multiple
trained keyword files. Letting each profile pick "Computer" or something
else ("Number One," "Bridge") would be a nice personalization touch and
exercises the same profile-switching machinery idea #2 needs anyway.

## Productivity and integrations

**8. Natural-language reminder due dates.** `add_reminder` currently passes
whatever text Claude extracts straight to Todoist. Real due-date parsing
("remind me to call the dentist tomorrow at 3") into Todoist's `due_string`
field would make reminders feel a lot less like typing a task manager and
more like actually talking to someone. Lives in
`desktop/core/actions/integrations.py`.

**9. Weekly captain's log digest.** A scheduled (not voice-triggered)
summary pulling from Soliloquy journal entries and completed Todoist
reminders into one spoken or written "week in review," delivered on a
routine trigger like "good morning" on Mondays specifically. Reuses the MQTT
coupling the `journal_entry` plugin already established with Soliloquy.

**10. System status queries.** "What's my battery at," "how much disk space
is left," as new built-in, fully deterministic actions, no AI round-trip
needed, similar in spirit to `get_weather`. Small, self-contained,
`actions/system.py`.

**11. Smart home bridge plugin.** A plugin analogous to `journal_entry_plugin.py`
that publishes to a Home Assistant MQTT topic, so "lights off" or "set the
thermostat to 68" flows through the exact pattern already proven with
Soliloquy, publish a small JSON payload, let another app do the real work.
Ships as a documented example plugin, same as `journal_entry`.

**12. Location-triggered routines.** Right now "leaving for work" only runs
when you say it. Android/iOS geofencing (WorkManager + Geofencing API on
Android, CoreLocation region monitoring on iOS) could fire the same
routines.yaml-equivalent macro automatically when you actually leave, no
voice command needed, opt-in per routine.

## Trust, safety, and debugging

**13. Local audit log for `run_command`.** The security module already
redacts and truncates command output before it reaches conversation
history; an opt-in local log (timestamp, command, redacted output) that a
new "show me today's command log" action can read back would give a
security-conscious user a full audit trail without changing the existing
confirmation gate at all. `desktop/core/actions/system.py`,
`desktop/tests/test_security.py` already has the test patterns to extend.

**14. Offline-mode self-benchmark.** `ensure_model_available()` already
exists in `core/ai.py`. Wrapping it in a one-shot "test yourself" action
that runs a fixed prompt through whichever backend is currently active and
reports latency would help someone decide, on their own hardware, whether
the Ollama fallback is actually worth leaving turned on.

**15. Plugin directory and installer.** The `ActionPlugin` pattern is solid
but discovery is entirely manual right now, copy a file into
`desktop/plugins/`. A `docs/PLUGINS.md` listing known community plugins
(starting with `journal_entry`) plus a tiny `scripts/install_plugin.sh
<url>` that fetches a plugin file and drops it in place would lower the bar
for anyone who isn't comfortable writing Python from scratch.

## Cross-platform

**16. Conversation hand-off between devices.** Each platform keeps its own
separate bounded conversation history today. A "continue this on my phone"
action that packages the current context into a small local file or QR code
would let someone start a conversation on desktop and pick it back up on
Android or iOS without repeating themselves.

**17. Shared routines across platforms.** `routines.yaml` is desktop-only
right now, Android/iOS have no equivalent trigger-phrase macro system. A
small shared, opt-in sync format (even something as basic as a JSON file
synced via iCloud Drive / a self-hosted endpoint) would let a routine
defined once apply everywhere, instead of desktop being the only platform
with instant, free, AI-free macros.

**18. Bridge status HUD (desktop).** A small always-on-top window showing
current mode (online/offline), the last wake event, and any command
awaiting confirmation, an LCARS-styled companion to `text_mode.py`, useful
for demoing the assistant or debugging without staring at raw log lines.
Desktop-only, cosmetic, and a good first project for anyone wanting to touch
the codebase without going near the security-sensitive parts.
