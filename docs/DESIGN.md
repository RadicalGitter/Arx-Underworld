# Score design and implementation

Status: implemented audition candidate, 2026-10-18. `mapping.csv` governs the
implemented cue assignments. This document explains the choices and their limits.

## Musical identities

Arx is a place of inhabited pockets within a threatening underground world.
An inhabited refuge should not sound like a tomb simply because both are dark.
Conversely, the abandoned dwarven industry needs absence and weight, rather
than the cheerful smithing stereotype a faction name could suggest.

| Arx space / change | Default music | Reason for the choice |
|---|---|---|
| Main menu | UW1 Introduction / Main Theme | A title-screen overture, activated directly by the engine. Continuous looping without regional silence intervals. |
| City streets and Yellow Tulip | UW1 Wanderer | Longer notes and a less busy texture than UW1 Descent; a recurring inhabited-world identity. Broad exploration testimony supports the family, not a proven cheerful mood. |
| Human outpost; troll spaces | UW1 Maps & Legends | A piece associated with conversation in UW1: social presence rather than automatic hostility. This exact emotional fit remains an audition hypothesis. |
| Goblin prison / abandoned goblin ruins | UW1 Dark Abyss | Low median note register and brooding exploration testimony support unease without constant combat intensity. |
| Goblin city | UW2 Prison Tower | A distinct, more active pattern than Dark Abyss, preserving the transition from abandoned passages to organized occupation. A listener praises the track; the institutional interpretation is ours. |
| General cave descent | UW1 Descent | More moving note activity than Wanderer, with support as effective labyrinth exploration music. Quiet gaps keep the environmental bed audible. |
| Ice caves | UW2 Ice Caverns | Specific listener testimony supports a haunting quality; loneliness fits the route. This is one of the stronger matches. |
| Rebel refuge / guarded state | UW1 Wanderer / Armed | Human kinship recurs, then the authored guarded cue adds pressure. No claim that all rebels are enemies. |
| Snake women's inhabited temple spaces | UW2 Scintillus Academy | A distinct lower-register pattern, reserved for their identity; atmosphere accounts describe elegance and unease. Music-specific emotional evidence is weak and marked accordingly. |
| Temple of Illusions / Noden | Brief UW2 Talorus/Ethereal Void excerpts | Busy high-register repetition creates a structural contrast; a listener finds this piece fatiguing. Use only 24 seconds followed by 70 seconds of quiet, at low gain. |
| Dwarven mines / foundry | UW2 Praecor Loth | Listener-described haunting music fits deserted industry better than a lively faction anthem. The mapping concerns the ruin, not dwarves as a people. |
| Crypt progression | UW2 Prison Tower, Praecor Loth and Scintillus | Controlled changes from confinement to solemnity to arcane unease; retain every separate strange-noise layer. Existing cues, rather than guessed room labels, decide where they occur. |
| Worm passage | UW2 Sewers | Sparse, unusually sustained notes leave room for environmental warning sounds. Replaces the initial, rejected choice of six-second UW1 Fleeing. |
| Ylside territory / climax | UW2 Killorn Keep-family / UW1 Combat | Sparse approach contrasts with denser confrontation; use the game's existing reveal and final-encounter cues. This does not imply a connection between the goblin and Ylside factions. |
| Ordinary combat / player danger | UW2 Combat | Player-only controller chooses UW2 Combat or Dangerous Situation from health with 30%/40% hysteresis; the original heartbeat cue is preserved exactly. Nearby combat intent and a quiet-period rule control lifetime; a confirmed engaged death can qualify for UW1 Victory. See COMBAT.md. |
| Authored discoveries and dramatic moments | Maps & Legends / Guardian's Trap | Existing camera and story cues only. Event function is known; specific emotional fit is less certain. |

See [listener research](VIBE-RESEARCH.md) and
[measured note structure](music-structure.json). Note density and register do not
prove emotion, harmony, instrument identity or listening quality. No automated
listening or video-transcript access is claimed. These are reasoned arrangements
to audition, not a completed human listening evaluation.

## Quiet space is part of the score

Regional pieces normally finish and leave 30–45 seconds of silence before
repeating. Only the especially busy Talorus material is excerpted by default.
Short encounter/story cues have no extra silence interval; their native scripts
still control lifetime and volume. Source imports get gentle edge fades and
static normalization to roughly -23 dBFS RMS, with a -3 dBFS sample-peak ceiling.
The table then scales the music down further, using an inverse logarithmic
conversion to Arx's volume controls (corrected in 0.1.2). This is RMS normalization, **not
LUFS loudness normalization or a true-peak limiter**.

The first musical excerpt begins when its native cue starts. There is no new
nearby-enemy detector, countdown, quest timer, secret detector, quest-name UI or
unrevealed plot-state polling. Walking slowly does not advance a music-mod timer
that changes game state. Reusing a native cue also means its music can be heard
in more than one place: the evidence table makes those shared uses explicit.

## How the files work

The tool reads original GAMB `.amb` files from the owner's SFX archive and loose
audio overrides. It leaves original environmental records byte-for-byte intact,
including position, pitch, volume, delays, key order, repeat counts and flags.
For explicitly selected musical beds in `replace_beds`, only the sample path
changes to an equal-duration PCM silent anchor. The anchor's frame length is
computed as Arx does, including the ADPCM `fact` clamp. No original sampled
sound is copied into the silent file.

In 0.2.0, new music lives in separate single-master AMBs. The original native
AMB keeps environmental tracks and silent anchors only; the menu retains its
independent hook. A player controller selects one music layer. NPC class
observers report intent and death without reading NPC health. Selected audio
calls use equal-width relays retaining their original commands and saved timer
offsets. No new timers, engine binaries, maps or save edits are introduced.

See [COMBAT.md](COMBAT.md) for priority, detection, fanfare eligibility, persistence,
script safety and known limits. Music changes stop/start, while environmental
zone crossfades retain native behavior. Speech ducking and playhead resumption
are not implemented. The installer journals backups and restores exact originals.

Some cave cues cover several unrelated rooms; this release cannot make each
secret chamber uniquely musical without additional map/script hooks. The castle
cue exists in the asset library but has no verified activation in the inspected
map/script set, so its suggested theme is disabled. Two other unused crypt cues
are disabled for the same reason. This release does not claim a separate active
theme for every crypt floor or a unique combat theme for every boss.

## 0.1.5 owner-requested music boost

`mix.json` applies +6.0206 dB after arrangement to the new musical WAVs only.
The original imported library is unchanged. Samples with sufficient headroom
are multiplied by two directly; otherwise FFmpeg's lookahead `alimiter` runs
with input gain two, output gain one, automatic level disabled, a -1 dBFS
sample-peak ceiling, 5 ms attack, 50 ms release, and latency compensation.
Every result must retain its original rate and frame count. Silent anchors
are never processed. Existing GAMB records, gains and the controller remain
identical. Peak protection can reduce the gain in loud passages; no true-peak
or subjective loudness target is claimed. FFmpeg is needed when limiting is
required, even if imported audio is already PCM.
