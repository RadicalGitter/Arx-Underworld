# Verification and native acceptance

Status: 0.2.0 offline-tested candidate. No game UI or live gameplay was observed.
Installation is recorded separately in integration-results.

2026-10-20 bunker music replacement: the owner reported repeated audible glitches
in the local UW2_13 rendition. All default assignments now use UW1 Armed instead
(39 enabled cues, 17 distinct pieces). The replacement's installed PCM WAV decodes
successfully; this is a technical check, not a listening assessment. The prepared
update retargets the single shared exploration AMB used by the bunker, approach
and city story changes. Its key bytes, volume and scheduling remain identical;
environmental AMBs, silent anchors, heartbeat and scripts are outside the update.
All 57 offline tests pass, including multi-cue retargeting, edit refusal, process
guard, interruption/resume and ordinary uninstall after an interrupted update.
The live update is prepared; installation and audible playback are pending Arx
being saved and closed. Private audio and update stages are not distributed.

2026-10-19 teleport/retreat repair: the emitted-script harness reproduced a
looping scripted pressure theme surviving a level change. Added regression
coverage for transition cleanup, quiet-time expiry/refresh, retreat without
victory, legacy-save migration and city-teleporter music recovery. The focused
updater is tested for concurrent owner edits, process guard, interruption before
and after the player write, idempotence, and exact ordinary uninstall. This
repair still requires an audible in-game teleport/retreat check after installation.

Installed 2026-10-19 after confirmed Clean shutdown. Only the player controller
and its music installation receipt changed; all 206 installed-file hashes match.
The full 19,609-byte original player script reconstructs exactly, with all 15
original timer positions retained. The previous controller and journal are in
the game's `.uwscore-state/router-updates/20261019T202516876382/`; the private
repair receipt is `.work/teleport-router-fix/installation-receipt.json`.
No game process or UI was launched for this verification.

| Check | Result |
|---|---|
| Tests | 32 passed: emitted ASL for groups, intent before damage, friend/hazard rejection, retreat, death, health hysteresis, boss priority, victory once/interruption, story expiry, reset and zone disambiguation. |
| Scripts | All 88 original scripts reconstruct to baseline hashes. Every original TIMER token keeps its byte offset. No new timers. |
| Callbacks | Two direct music timer relays use ACCEPT to preserve line-only execution. Ordinary events require explicit terminators. |
| Environment | 84 original records remain byte-identical; 17 music beds keep raw scheduling through exact-duration silent anchors. Heartbeat AMB is identical. |
| Music separation | Native AMBs retain only environmental/anchor tracks; music uses separate single-master, single-play-per-key AMBs. Menu keeps its native hook. |
| Independent parser | Every AMB in both payloads was also read with the upstream Arx Blender AMB reader. |
| Full payloads | Both 39-cue / 206-file payloads passed hashes, installation and exact uninstall. About 65.9 MiB test pads / 282.6 MiB private UW build. |
| Existing mods | Twelve intentional script overlaps with 1,072 Extended files. Original sources reconstruct and loose files restore; gameplay compatibility remains untested. |
| Package | 52-file kit (code, docs, tests, CC0 pads; no UW audio, Arx scripts/AMBs or builds). Tests pass from the unpacked kit, and its test-mode rebuild is byte-identical to the router build (206 files, 88 patches). |
| FFmpeg | Limiter uses native latency compensation on FFmpeg 5.1+; older versions (checked on 4.4) use a measured pad-and-trim fallback that keeps exact length and sample alignment. |
| Save loads | Fixed: region state moved from unsaved player locals to saved globals. Harness tests load a save outside the trigger zone, a save with no state, and a different save (no stale region). 36 tests pass. |
| Source | Relevant paths inspected in 1.2.1 and recorded 1.3-dev. No engine compilation/runtime test claimed. |

[Machine-readable results](integration-results.json). Run
`python -m unittest discover -s tests -v` without proprietary inputs. The harness
executes only the used ASL subset; it is not the native interpreter.

## Game-side checks

1. Load an existing save, check logs, change levels and reload a router-era save.
2. Cross city, outpost/tavern, goblin, troll, snake and crypt boundaries, including
   duplicate zone names. Check music identity and environmental sound.
3. Let an enemy approach before damage. Drawing a weapon near friends or taking
   hazard damage should not start music.
4. Fight two enemies. No victory after the first; after the last dies, wait six
   seconds (ten with weapon raised), hear one fanfare, then exploration. New
   aggression must interrupt the fanfare.
5. Retreat without a kill: no fanfare. Test ranged casters, pursuit, instant kills
   and unusual actors.
6. Cross 30% health, heal to 35%, then 40%: danger, danger, recovery. No repeated
   restarts or changes based on NPC wounds. Repeat during a boss fight.
7. Test discoveries, cameras, Black Beast, crypt and final boss phases. Check one
   musical layer, environmental sound and dialogue clarity.
8. Test death, reload, pause/menu and level changes. No victory for player death
   or just reloading. Menu retains UW1's theme.
9. Close Arx, uninstall, restart and verify prior files. Saves may retain mod
   ambience references; no save conversion is performed.

Mood/rendition matches remain audition candidates. Castle/unobserved crypt hooks
stay disabled. No global roster, music crossfade, speech ducking or new quest/map
logic is implemented.

Live installation: all 206 files match the build. Twelve existing script paths
were patched, with originals reconstructable; 648 other protected game/settings/
save files match the fresh pre-update snapshot. No game process was launched.
