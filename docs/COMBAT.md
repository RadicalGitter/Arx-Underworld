# Combat detection, exclusive music and victory

Status: 0.2.0 offline-tested candidate. Native playback still requires an audition.
`combat.json` controls the heuristic; `mapping.csv` controls roles and priorities.
`mix.json` retains the +6.0206 dB music boost.

## Behavior

- Nearby NPCs targeting the player in fight, magic, ranged, pursuit/search or
  fleeing behavior report threats. Scanning happens once per game second, with
  delivery on engine heartbeats. Damage is no longer required to start music.
- The local radius and portal-based walking-distance limit are 2,200 units.
  Friendly NPCs, drawing a weapon, and environmental damage alone do not qualify.
- Normal combat uses UW2 Combat. At 30% player health it changes to UW2 Dangerous
  Situation; healing to 40% restores normal/boss music. No NPC health is queried.
- Six quiet seconds after the last threat end combat; ten with a raised weapon.
  New threat reports extend the encounter.
- The Black Beast's scripted pressure request also expires after ten seconds
  without a nearby threat, and is cleared when a battle ends. Its pre-combat
  cue can still start immediately; it cannot loop indefinitely after escape.
- UW1 Victory plays once after an engaged enemy's reported death and a clear
  local encounter. An intervening live threat clears eligibility until another
  engaged death is reported. Escape alone, hazards, player death and loading a
  save do not qualify. A new attacker interrupts the fanfare.
- Exploration returns after victory or retreat, starting its piece again.

## Exclusive music

Default priority: exploration, story, normal combat, boss combat, low-player-
health danger, victory. Boss requests are eligible during an active local battle.
Black Beast pressure remains a story layer that can precede combat.

Every change stops this mod's previous music before starting the selection.
Reasserting the same non-fanfare cue only adjusts volume. The fanfare uses
separate once-only and volume commands to support 1.2.1's flag limitation.

Native AMBs now contain their original environmental records and silent music
anchors, with no appended UW music except the independent menu theme. Music uses
separate non-positional AMBs. The controller never uses `ambiance kill`.
Environmental records, heartbeat and timing anchors are unchanged. Original game
scripts' own kill commands retain their behavior.

Music switches immediately. Beat matching, crossfading, speech ducking and
playhead persistence are not implemented. Native environmental crossfades remain.

## Scripts, zones and persistence

The builder reads complete local scripts and overlays the owner's loose mods.
Selected AMBIANCE/ZONEPARAM calls use fixed-width GOSUB slots and appended relays.
Each relay executes the original native audio command verbatim, then notifies
the player. Every original timer-command offset is preserved; no timers are
added. Direct timer callbacks end with ACCEPT to preserve line-only execution;
ordinary relays RETURN. Unsupported asynchronous contexts and events without
explicit terminators are rejected.

The existing GAME_READY entry runs a reset through a fixed-width slot: the
native player does not receive the ordinary LOAD callback on save restoration.
An appended RELOAD handler covers level changes. It clears old story/boss
requests, expiry times, the encounter/fanfare, regional identity and the zone
latch before the destination is evaluated. Leaving a fight does not award victory.
Save restoration preserves current-format regional/story globals; a separate
encounter-state revision clears legacy unbounded requests once per old save.

`combat.json` also defines observed regional fallbacks. Arx city has no musical
DLF zone, so its two verified fixed notices (`public_notice_0002` and
`public_notice_0010`, both internal level0 only) select `ambient_town` during
reset, including arrival at the teleporter. An absent landmark cannot match.
Other destinations recover through existing zone and native script cues.

Arx Libertatis never saves the player entity's own local variables (it is
skipped by `Push_AllIO`, and `Pop_Player` restores no script variables), so the
region, its volume, the zone latch, story/boss volumes and expiry times live in
saved globals (`#uwsc_*`, `&uwsc_*`). A save therefore restores its own music
region even when loaded away from the zone that started it (e.g. inside the
goblin city, whose music is set at the FIRETORCH gate zone). Saves made before
this change carry no state; their music returns at the next routed zone. A mapping revision identifier
invalidates stale numeric IDs. Old ordinary-combat AMB names remain as silent
migration resources.

There are 50 observed zone routes. Two fixed landmarks per level disambiguate
generic zone names in [zone-music.json](zone-music.json). If both are absent, the
route is not guessed. Native script region changes persist until a different
musical zone or request changes them.

### Updating only the controller

`router_update.py prepare --game-dir GAME --manifest PRIVATE_BUILD/mod-manifest.json
--output NEW_PRIVATE_STAGE` reconstructs the exact installed player baseline
and emits a controller-only update. The source manifest and installation journal
must both match the current player checksum. Stages contain private game script
bytes and must not be redistributed.

After saving and closing Arx, use `router_update.py apply --game-dir GAME --stage
NEW_PRIVATE_STAGE`. It checks that the process is closed and the log reports
Clean shutdown, backs up the installed controller and journal, and updates only
the player script and its installation receipt. Original uninstall backups stay
unchanged. Interrupted writes recover through `router_update.py recover` or the
ordinary uninstaller; owner edits cause rejection. No audio rebuild is needed.

The private payload changes 88 script paths, including 12 Extended overlaps.
Before-images, hashes, fixed-width replacement records and appendix hashes allow
exact reconstruction and uninstall. Maps, saves, engine binaries and existing
gameplay commands are not rewritten. Added NPC code changes no behavior, target,
damage, health, loot or quest state; it reports intent and death only.

## Limits

This is a local heuristic, not a global combat roster. Distant attackers,
customized scripts refusing probes and unusual target/behavior states can be
missed. Death reports can lag until the corpse's next heartbeat. Instant kills
before the first probe, bodies immediately destroyed by their death handler,
or custom instance scripts refusing DEAD can omit victory.

Observers cover all 32 NPC class scripts in this baseline. Thirty-one accept an
appended DEAD observer. The existing `flying_creature` DEAD handler is preserved;
its death does not independently qualify. Existing death handlers are not replaced.
Boss phases, ranged attacks, corner pursuit, existing-save loads and the audible
mix still need native testing. The ASL-subset harness is not Arx's interpreter.

## Configuration and evidence

Settings: `threat_radius`, `quiet_seconds`, `armed_quiet_seconds`,
`minimum_battle_seconds`, `low_health_fraction`, `recovery_health_fraction`.
Disable `music_router` for the previous damage/health controller or disable
`enabled` to omit it. Rebuild/reinstall after changing settings.

Inspected 1.2.1 and 1.3-dev source: Script.cpp, ScriptedLang.cpp, ScriptEvent.cpp,
ScriptUtils.cpp, ChangeLevel.cpp, Damage.cpp and ai/Paths.cpp. References:
[variables](https://wiki.arx-libertatis.org/Script:Variables),
[events](https://wiki.arx-libertatis.org/Script:sendevent),
[timer offsets](https://wiki.arx-libertatis.org/Script:timer).
UW's [reverse-engineered damage code](https://github.com/hankmorgan/UnderworldGodot/blob/main/src/interaction/damage.cs)
supports the normal/losing distinction. Opponent-health winning themes are
deliberately excluded; retail UW timing is not claimed.
