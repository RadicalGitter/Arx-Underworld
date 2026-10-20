# Arx Underworld Music 0.2.0

Version 0.2.0 is installed and file-verified in Oscar's game. The build passes
offline checks. Music
is separated from environmental AMBs and routed exclusively. The UW1 menu theme,
+6.0206 dB music gain and peak protection remain.

Nearby hostile intent starts combat before damage is required. Six quiet seconds
end it, extended to ten with a raised weapon. Player-health switching remains
30% danger / 40% recovery. NPC health is not queried. An engaged enemy's reported
death followed by a clear local encounter triggers UW1 Victory once; new
aggression interrupts it. Pure escape and player death do not qualify.

Instant kills before a probe, removed bodies and unusual/custom NPC scripts can
omit victory. Combat beyond the scan radius is not tracked. Native playback,
boss transitions, saves and mix remain unverified. Exploration restarts its piece.
See [combat rules and limits](docs/COMBAT.md).

The kit has 39 cues, 18 active UW pieces, a 46-row mapping, original CC0 test pads
and local import/render tools. It includes no UW music, extracted Arx scripts or
assets, ROMs, SoundFonts, engine binary or private build.

Verification: 32 unit/scenario tests; independent parsing of both complete
payloads; exact preservation of 84 environmental records, heartbeat and 17 timing
anchors; reconstruction of all original scripts/timer offsets; full reversible
installation with audio/script/save/config sentinels. The native interpreter
and audio engine have not been tested.

The private payload has 206 files, including 88 script paths. Twelve overlap the
audited Extended archive. Changes are appended observers/controllers and 132
fixed-width audio/bootstrap slots. Original commands remain in relays and every
original byte reconstructs. No maps, saves, engine binaries or existing gameplay
commands are rewritten. Installation backs up originals and rejects conflicts.

Research, compatibility and an in-game checklist are under `docs/`. The download
ships test pads only; import legally sourced recordings or render your own XMI
library for the UW version.

Packaging: the 52-file kit was audited for private content, its tests pass when
unpacked, and its test-mode rebuild is byte-identical to the verified build.
The peak limiter now also works with FFmpeg older than 5.1.

Save-load fix: exploration music is now restored on loading a save anywhere
(previously silent until the next trigger zone, e.g. inside the goblin city),
because its state moved to saved globals. Only the player script changed;
music files are byte-identical to the previous install.

Live installation: all 206 files match the build. Twelve existing script paths
were patched, with originals reconstructable; 648 other protected game/settings/
save files match the fresh pre-update snapshot. No game process was launched.
