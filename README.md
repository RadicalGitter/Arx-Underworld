# Arx Underworld Music - 0.2.0 audition build

An installable Arx Libertatis music kit using locally imported UW1/UW2 music,
while retaining Arx's environmental sounds.

**39 cues use 17 pieces, with a 46-row editable mapping.** Music is separated
from ambience and only one musical layer is selected at a time. Nearby hostile
intent starts combat before damage is required. Six quiet seconds (ten with a
raised weapon) end it. A reported engaged-enemy death followed by a clear local
encounter can trigger UW1 Victory once. Player health still switches danger at
30% / recovery at 40%; NPC health is never queried by the added music code.

The UW1 menu theme and +6.0206 dB boost remain. Offline tests pass; native playback,
save loads and mix still need an audition. See [combat rules](docs/COMBAT.md).

The download contains original, CC0 test pads. It contains **no Ultima music,
ROMs, SoundFonts, game scripts or extracted Arx assets**. The builder reads the
owner's audio and complete script baseline locally. Observers are appended;
selected audio calls use fixed-width relays. Original timer byte offsets are
preserved and no timers are added. Private patched game scripts are not shared. Private builds and imported music must stay local.

## Install the test version

Requirements: Python 3.10 or newer, FFmpeg on PATH for safe peak limiting (any recent version; 5.1+ preferred), the PC Arx game data, and Arx Libertatis with
its `arxunpak` tool. Windows is the tested platform. Extract this kit somewhere
writable, outside the game folder. Close Arx before changing its audio.

From a terminal in this kit's folder:

```powershell
python score.py setup --game-dir "C:\Games\Arx Fatalis" --mode test
```

On Windows you can instead drag the game folder onto `Install-Test-Mod.cmd`, or
run that file with the game folder as its first argument. This installs the
included test pads so you can check that the cues change in the right places.
Those pads are functional placeholders, not previews of Ultima's melodies.

If Arx Libertatis and the PAK files are in different folders, point `--game-dir`
at the folder with `SFX.pak` and pass
`--unpacker "C:\Path\To\Arx Libertatis\arxunpak.exe"`.
The game must actually load that data directory. Check `arx.log` if in doubt.

## Use the Ultima soundtracks

See [the local import and rendering guide](docs/IMPORT.md). It supports either
your own rendered recordings, or an offline FM rendition from your own XMI files
using an external libADLMIDI tool. The latter route was exercised with both games;
it is **not an authentic Roland MT-32 recording**.

To let a coding agent do the work, give it the prompt in
[docs/AGENT-PROMPT.md](docs/AGENT-PROMPT.md): it looks for your own copies of the
games first and falls back to a personal-use YouTube download only if you agree.

After importing your library into `assets`, uninstall the test version, then:

```powershell
python score.py setup --game-dir "C:\Games\Arx Fatalis" --mode underworld --assets assets
```

The Windows equivalent is `Install-Underworld-Mod.cmd "C:\Games\Arx Fatalis"`.
Its optional second argument selects a different imported-asset directory.
No command launches the game, downloads music or starts an ongoing service.

## Uninstall or recover an interrupted install

```powershell
python score.py uninstall --game-dir "C:\Games\Arx Fatalis"
```

Or drag the game folder onto `Uninstall-Mod.cmd`. Previous loose audio and every patched script are
restored from checksummed backups; newly added files are removed. Backups
and a removal receipt remain in `.uwscore-state` in the game directory. If a
file was edited after installation, uninstall stops before changing anything,
so that edit can be preserved. An interrupted install/uninstall can be recovered
by rerunning uninstall. Do not delete the state directory to bypass recovery.

## Edit the score

Open [mapping.csv](mapping.csv) in a text editor or spreadsheet. Its rows name
the real native `.amb` cue, imported track ID, gain, silence interval, optional
excerpt length, actual area/zone/script evidence, mood rationale and confidence.
Gains are linear amplitude targets, converted to Arx's logarithmic controls
when building. The table contains spoilers in its location/evidence columns. Change `enabled`
to `0` to leave a cue entirely vanilla. Do not rename native cues casually. `combat.json` controls the 30% danger /
40% recovery thresholds. The `role` and `priority` columns control routing. Generated combat/victory
rows use music-only AMBs. Native `ambient_fight` stays heartbeat-only.

UW1 Armed now covers every former UW2 Killorn Keep / Pits of Carnage assignment.
The previous local rendition produced owner-reported glitches in the bunker.
Its catalog/import entry remains available, but it has no default assignments.

For an existing installation, `music_update.py` can retarget exploration cues
to an arrangement already installed for another cue, without changing scripts
or environmental tracks. Change all affected mapping rows first, then prepare
and apply a private stage (close Arx before applying):

```powershell
python music_update.py prepare --game-dir "C:\Games\Arx Fatalis" --source uw2_13 --replacement uw1_10 --stage .work/bunker-music-update
python music_update.py apply --game-dir "C:\Games\Arx Fatalis" --stage .work/bunker-music-update
```

The updater checks installed hashes, retains before-images and updates the
ordinary uninstall journal. Rerun apply after interruption, or uninstall normally.
It requires matching excerpt/rest arrangements and exploration-only cues; changes
to combat, story or victory durations require a full rebuild.

For a controlled build and preview of the install operation:

```powershell
python score.py extract --game-dir "C:\Games\Arx Fatalis" --output .work/original
python score.py build --original .work/original --assets assets --output .work/my-score --gain-scale 0.8
python score.py verify --payload .work/my-score
python score.py install --payload .work/my-score --game-dir "C:\Games\Arx Fatalis" --dry-run
python score.py install --payload .work/my-score --game-dir "C:\Games\Arx Fatalis"
```

Use a new empty build folder each time. Uninstall the previous version before
extracting a fresh baseline or installing another version. Keep the Ambience
volume at your preferred environmental level and adjust this mod's `gain` or
`--gain-scale` to balance the new music separately. New music still uses Arx's
ambience mixer; it has no new in-game volume slider.

`--keep-original-music` on `build` retains every original track, including the
musical beds otherwise replaced. This option can reintroduce native music
over the routed score, so leave it off when testing exclusive music. Footsteps, dialogue, weapons and local effects
are never replaced by this kit.

## Compatibility and evidence

- [Design, theme choices and limitations](docs/DESIGN.md)
- [Mood research: listener observations versus inference](docs/VIBE-RESEARCH.md)
- [Arx audio/source/map research](docs/RESEARCH.md)
- [Compatibility: 1.2.x, 1.3-dev, Arx Extended](docs/COMPATIBILITY.md)
- [Verification and in-game acceptance route](docs/VERIFICATION.md)
- [Soundtrack IDs](tracks.csv), [bulk import template](import.csv)
- [Licensing](LICENSE.txt)

Development source belongs in `Z:/Programmering/Projects/Games/ArxUnderworldMusic`.
The portable release is a snapshot of that source, not a second editable project.

## Music level

Version 0.2.0 (normalised): every track is measured (EBU R128) and normalised to
`music_target_lufs` in `mix.json` (-20 LUFS) with the -1 dBFS peak limiter; all cues use
the same gain (0.9, about 4 dB louder than the original game music) and the router plays every piece at one fixed volume, so no zone or
script makes one piece louder than another. Environmental ambience (wind, drips,
crowd noise) is lowered by `environment_gain_db` (-6 dB) by shifting only the volume
field of those records; the heartbeat is untouched. Change either value and rebuild.

### Earlier behaviour

Version 0.1.5 adds +6.0206 dB (twice the sample amplitude) to music only,
including menu and combat. `mix.json` controls this rebuildable gain. A -1 dBFS
sample-peak limiter protects loud peaks; those sections rise by less than 6 dB.
This is not a promise of twice the perceived loudness or a true-peak guarantee.
Imported originals remain untouched. Environmental tracks, heartbeat, timing
anchors, per-location balance, and player-health switching are unchanged.
Set `music_boost_db` to 0 and rebuild to return to the 0.1.4 music level.
