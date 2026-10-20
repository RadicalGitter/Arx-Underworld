# Arx Underworld Music

> This file is the agents' domain: written by agents, for agents. Keeping it accurate and current is the job of whichever agent works here; Oscar does not read or maintain it. Rules Oscar stated in it remain his decisions: record them faithfully and change them only when he does.

Follow `Z:/Programmering/AGENTS.md` and the instructions in the current chat.
This project owns the mod source, editable cue mapping and documentation.
Oscar plans to publish this repository as a public mod (2026-10-20). Keep every
tracked file publishable: no Ultima or Arx assets, extracted data or private paths
beyond this workspace's own instructions; check the history before it goes public.
Do not distribute Ultima music, soundfonts, ROMs, Arx game assets, or local builds.
Keep owner-provided assets and extracted data in ignored `.work/`.
The owner retired the glitchy local UW2_13 rendition on 2026-10-20: every former
assignment now uses UW1 Armed (uw1_10). Keep the old catalog/import record for
optional assets, but do not silently reintroduce it into default mappings.
`music_update.py` performs guarded exploration-only retargets to already-installed
arrangements, with backups, resumable journaling and ordinary uninstall recovery.
Never replace maps, saves or engine binaries for this mod.
Player-health music is explicitly authorized: append a player-only controller
to the owner's existing player script, retaining reconstructable original bytes
and timer offsets. A fixed-width GAME_READY reset relay is permitted alongside
audio relays. Back up and restore originals exactly; reject conflicting MAIN
handlers. Never read NPC health or modify combat/gameplay behavior.
The owner requested exclusive music, tighter combat detection and victory music.
For that scope, append read-only combat-intent/death observers to NPC class
scripts. Route selected native audio calls through equal-width GOSUB slots and
appended relays that execute the original audio command verbatim. Preserve all
original timer-command byte positions; no new timers or edits to existing
gameplay commands. Retain reconstructable before-images and exact uninstall.
Keep environment/heartbeat AMBs separate from exclusively routed musical AMBs.
Preserve environmental AMB tracks as raw bytes except the owner-requested uniform
volume shift (mix.json environment_gain_db, default -6 dB); the heartbeat stays untouched. Changes to musical tracks must
retain their scheduling through equal-duration silent anchors.
Use only observed zone/script hooks; distinguish shared cues from unique ones.
Run `python -m unittest discover -s tests -v` before packaging.
Build into a local folder (e.g. $HOME/build), not .work on the network share: writing the
~280 MB payload over the share exceeds tool time limits. Normalised music is cached in .work/music-cache.
Controller state that must survive save loads goes in global (#/&) variables:
Arx never saves the player entity's local variables.
Do not launch or inspect game UI without Oscar's explicit browser/computer-use approval.

Read `README.md` for operation, `docs/DESIGN.md` for cue design and limits,
`docs/RESEARCH.md` for source evidence, and `docs/VERIFICATION.md` for test status.

The main menu must use UW1's main theme (UW01.XMI). Mapping gains express
linear amplitude targets; convert them to Arx's logarithmic controls when building.
Do not write linear values directly into GAMB volume keys.
The owner later asked for normalised music volume (superseding the flat +6 dB boost):
every music track is normalised to mix.json music_target_lufs (-20 LUFS, EBU R128,
-1 dBFS peak limiter), all mapping gains are equal (0.9; raised +5 dB at the owner's request, ~4 dB above the original game music), and the router plays every
music layer at one fixed volume (routing.MUSIC_VOLUME). Keep heartbeat and silent
timing anchors unchanged. Preserve raw imported assets for reversible rebuilds.
