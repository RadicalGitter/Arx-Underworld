# Arx audio and location research

Supporting research, not a claim of runtime acceptance. Sources inspected on
2026-10-18. The local original files are not distributed.

## Primary implementation evidence

Arx Libertatis master source was inspected at
[`5b95e4c5ca9d583f1b11c085326979772645e0f3`](https://github.com/arx/ArxLibertatis/tree/5b95e4c5ca9d583f1b11c085326979772645e0f3),
and compared with tag [`1.2.1`](https://github.com/arx/ArxLibertatis/tree/1.2.1).

- [`src/audio/Ambiance.cpp`](https://github.com/arx/ArxLibertatis/blob/5b95e4c5ca9d583f1b11c085326979772645e0f3/src/audio/Ambiance.cpp): GAMB header, versions 1.0.0.2/3, sample paths, 116-byte key records, reverse key loading for v3, master restarts and source repeat counts.
- [`src/scene/GameSound.cpp`](https://github.com/arx/ArxLibertatis/blob/5b95e4c5ca9d583f1b11c085326979772645e0f3/src/scene/GameSound.cpp): ambience root, two-second zone fade, script volume updates, stopping by volume zero, separate zone/script lifetimes.
- [`src/script/ScriptedControl.cpp`](https://github.com/arx/ArxLibertatis/blob/5b95e4c5ca9d583f1b11c085326979772645e0f3/src/script/ScriptedControl.cpp): `ambiance` and `zoneparam` behavior. The 1.2.1 flag parser returns before handling combined once/volume flags, unlike development source.
- [`src/scene/LoadLevel.cpp`](https://github.com/arx/ArxLibertatis/blob/5b95e4c5ca9d583f1b11c085326979772645e0f3/src/scene/LoadLevel.cpp) and [`src/ai/Paths.cpp`](https://github.com/arx/ArxLibertatis/blob/5b95e4c5ca9d583f1b11c085326979772645e0f3/src/ai/Paths.cpp): a DLF record must have nonzero height and the ambience flag to count as a music-bearing zone; entering that zone invokes the native cue.
- [`src/audio/codec/WAV.cpp`](https://github.com/arx/ArxLibertatis/blob/5b95e4c5ca9d583f1b11c085326979772645e0f3/src/audio/codec/WAV.cpp) and [`ADPCM.cpp`](https://github.com/arx/ArxLibertatis/blob/5b95e4c5ca9d583f1b11c085326979772645e0f3/src/audio/codec/ADPCM.cpp): PCM support, ADPCM fact/sample-count clamp; basis for equal-duration silent anchors.
- [`src/io/resource/ResourceSetup.cpp`](https://github.com/arx/ArxLibertatis/blob/5b95e4c5ca9d583f1b11c085326979772645e0f3/src/io/resource/ResourceSetup.cpp): loose `sfx` resources participate after archives. Another data directory can still win precedence.

The independent Python implementation preserves raw records rather than copying
the engine's GPL source. The upstream Blender AMB reader was used separately as
a cross-check. Its DLF reader and the locally installed ArxIO DLL were used for
research only, not bundled into this kit.

Documentation cross-checks:
[file formats](https://wiki.arx-libertatis.org/Filetypes),
[ambiance](https://wiki.arx-libertatis.org/Script:ambiance),
[zoneparam](https://wiki.arx-libertatis.org/Script:zoneparam),
[modding tools](https://wiki.arx-libertatis.org/Arx_Fatalis_tools).

## Spatial grounding

World depth and internal area number are different. The
[official world map index](https://wiki.arx-libertatis.org/World_of_Arx_Fatalis)
and [Aldernon NL's mapped walkthrough](https://steamcommunity.com/sharedfiles/filedetails/?id=318768749)
were cross-checked against local DLF zones and scripted object identities.

| World map depth | Relevant internal areas |
|---|---|
| 1 | Castle 0; city 11; outpost/Yellow Tulip 12; council room 8 |
| 2 | Goblin prison/ice caves 1; crystal caves 13; Akbaa temple 14 |
| 3 | Goblin city/troll mines 2; abandoned goblin region 15 |
| 4 | Caves and lake approaches 3; rebel camp 16; Crypt I 17; lake area 20 |
| 5 | Ylside bunker 4; caves 18; Crypt II 19 |
| 6 | Edurneum/Temple of Illusions 5; Crypt III 21 |
| 7 | Mushroom forest/worm tunnel 6; Crypt IV 22 |
| 8 | Dwarven mines/forge/foundry 7; Crypt V 23 |

The retained [cue evidence index](cue-evidence.json) records actual zone names,
script paths/line numbers and entity-to-area membership. It contains spoilers.
[amb-inventory.json](amb-inventory.json) records the inspected sample references,
versions and track flags without redistributing the audio. A stored ambience
string with no active zone flag was not accepted as an activation hook.

Examples with concrete activation evidence include goblin/troll zones in area 2,
snake/illusion zones in area 5, dwarf/lava zones in area 7, the tavern's native
zone in area 12, rebel states in area 16, temple-distance cue `marker_0481` in
area 14, crypt cue `marker_0253` in area 22, and authored discovery cameras in
areas 4 and 5. `ambient_bunker` also appears in city scripts, so it is not
presented as a unique secret-location detector.

## Soundtrack and mood evidence

[Underworld Adventures' game-format research](https://github.com/vividos/UnderworldAdventures/blob/main/uwadv/docs/uw-formats.txt)
anchors the original XMI identifiers. Track titles are not reliable mood labels,
and multiple places can share one file. [VIBE-RESEARCH.md](VIBE-RESEARCH.md)
records the first-hand listener/player sources and weak or inaccessible evidence.
[music-structure.json](music-structure.json) records measured duration, note
density, register and sustained-note statistics from the owner's XMI files.
XMIDI timing was interpreted at 120 ticks/second; these statistics exclude
channel-10 percussion. They describe structure, not perceived emotional valence.

The optional rendering route was verified using the
[libADLMIDI 1.6.2.1 release](https://github.com/Wohlstand/libADLMIDI/releases/tag/v1.6.2.1)
and its published CLI/source. It is an external tool, not a dependency in the
game-ready audio. Its source was not modified and is not redistributed here.

## Combat and volume follow-up

The installed player script's `ON OUCH` starts `ambient_fight`; its existing
end/death paths stop that ambience. 0.1.3 appends music while retaining the
original heartbeat record. This does not identify hostility or health state.
See [combat limitations](COMBAT.md).

`src/audio/openal/OpenALSource.cpp::updateVolume` in both 1.2.1 and the inspected
development source uses a logarithmic control curve. The initial kit had treated
those values as linear amplitudes, causing the observed near-silent music.
The inverse conversion and engine-formula regression test correct that error.

## 0.1.4 player-health controller

The owner requested player-health switching with no NPC-health adaptation. Both
1.2.1 and inspected 1.3-dev provide `^player_life`/`^player_maxlife`.
`ARX_SCRIPT_AllowInterScriptExec` sends MAIN heartbeats to treat-zone entities;
Player.cpp explicitly puts the player in that zone. The installed Extended
player script has no MAIN handler/main-event override, so a new handler can be
appended without shifting saved timer byte offsets. No new timers are added.
Repeated PlayScriptAmbiance calls only update volume for an existing ambience;
zero deletes it. Thus repeated reassertion recovers missing playback after a
load without repeatedly restarting the same theme. These are source findings,
not observed runtime behavior. COMBAT.md governs the threshold and limitations.

## 0.2.0 routing and combat source findings

Player GAME_READY is broadcast by Core.cpp, while its direct Player.cpp script
load bypasses ordinary NPC LOAD dispatch. ChangeLevel.cpp sends RELOAD for level
changes. Thus a fixed-width GAME_READY bootstrap is necessary; LOAD alone is
insufficient. ScriptedVariable.cpp registers DEC, not SUB, for subtraction.
ScriptEvent.cpp changes EXECUTELINE to DUMMY after GOSUB; direct audio timer
relays must ACCEPT instead of RETURN to retain original line-only execution.
The two direct callbacks and all original timer offsets were audited.

NPC behavior letters f/m/d/o/e plus target PLAYER provide combat-intent signals.
Damage.cpp changes dead NPC main events to DEAD; appended DEAD handlers provide
conservative death reports without querying NPC health. The existing flying-
creature DEAD handler is preserved. GAMB master keys use one sample play, with
native looping or once-only mode. Native environmental tracks remain separate.

Fifty zone routes are grounded in the extracted maps. Generic duplicate names
are area-qualified using two fixed landmarks from the extracted entity-area
index. Integration results and COMBAT.md record implementation limits.
