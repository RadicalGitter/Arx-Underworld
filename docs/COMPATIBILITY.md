# Compatibility

Status as researched on 2026-10-18. Offline file compatibility is distinct from
completed playtesting.

| Target | Basis / limitation |
|---|---|
| Arx Libertatis 1.2 / 1.2.1 | Main target. Local 1.2.1 installation and real SFX resources inspected. PCM WAV and GAMB versions used by this kit are supported by the 1.2.1 source. Playback has not been exercised. |
| Arx Libertatis 1.3-dev | Source inspected at commit `5b95e4c5ca9d583f1b11c085326979772645e0f3`. Same core GAMB/WAV approach; do not describe this as tested against a released 1.3. |
| Original Arx Fatalis executable | Not qualified. Use Arx Libertatis for this kit. |
| Arx Extended 2.3.5 | Twelve intentional script overlaps in 0.2.0. All original bytes reconstruct through fixed-width audio slots and appended observers. Original timer positions remain unchanged. Maps, models, translations and speech are not modified. Gameplay compatibility still needs testing. |
| Other audio/overhaul mods | Build from the actual installed audio baseline. Loose WAV/AMB overrides in the selected game directory are included by `extract`. Overhauls with renamed cues, changed masters, new sample formats, extra PAKs or another higher-priority data directory require a separate audit. |

The [official download page](https://arx-libertatis.org/download) still identifies
1.2.1 as the current release and lists development snapshots separately. Its
1.3-dev entry is not a promise of a stable 1.3 release.

The [ambiance command documentation](https://wiki.arx-libertatis.org/Script:ambiance)
warns that before 1.3, `-v` and `-n` cannot be combined. The fanfare uses
separate once-only and volume calls; other music uses `-v`. Variables, radius
events, player/dead heartbeats and GOSUB behavior were checked in the inspected
versions. Mono PCM remains the common output. No new engine binary is needed.

## Arx Extended details

The official mod-list mirror's `AFE235.rar` was downloaded and its MD5 verified
as `de99752b92bc67d8e8a35e16749c2994`. Its included readme still displays 2.3.4,
so the archive name and checksum, rather than that stale header, identify the
audited artifact. See the [official mod list](https://wiki.arx-libertatis.org/Arx_Fatalis_mods).

Extended's own instructions require a new game for installing Extended because
it changes gameplay/scripts. This kit does not edit saves. It adds local music
variables and fixed-width audio relays while preserving original timer offsets
and adding no timers. A new game is not expected to be required, but existing
save restoration needs native verification. Install Extended first under its
own instructions; do not reinstall it as part of a music update. Rebuild from
current installed scripts after another mod changes them. See [combat details](COMBAT.md).

## Data directories, saves and volume

Install into the actual data directory Arx uses; launcher folders can differ
from PAK locations. Files in another configured data/user directory can override
these files. The installer checks its target, but cannot prove the game's final
resource resolution without an actual launch/log review.

Because ambience is saved by name and type, a restart and save reload should use
the replaced resource; the exact restored position is not promised. Check an
existing save and an area transition during acceptance. No save conversion is
performed and no existing game process is touched.

The mod's new music and environmental ambience share Arx's Ambience slider.
Adjust table gains to reduce music without reducing environmental effects.
Headroom, mono PCM and restrained gains help preserve intelligibility; final
mixing still depends on source rendition, headphones, scene and user settings.

## Linux / macOS

The Python code is portable, but only Windows was tested. Pass the native
`arxunpak` executable explicitly. Respect file case and avoid parallel `SFX` and
`sfx` trees; generated paths are lowercase. The Windows CMD helpers are optional.
No launch, OS installation or native packaging on those systems was tested.
