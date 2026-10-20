# Local soundtrack import

Use recordings or game assets you are entitled to use. The tools do not fetch
soundtracks. Ownership of the games does not make the music public-domain.
Keep imported WAVs, extracted files and game-ready builds private. Share the
kit, mapping and original placeholders instead.

A ready-made prompt for a coding agent that does all of this for you is in
[AGENT-PROMPT.md](AGENT-PROMPT.md).

## Import rendered recordings

`tracks.csv` identifies source track numbers independently of inconsistent album
titles. Supply one complete rendition per ID. Prefer consistent instrumentation
and recording levels across the collection; an MT-32 recording, OPL rendition
and orchestral cover can have very different moods despite sharing note data.
Avoid mixing those styles accidentally. Licensed recordings and arrangements
can also have their own usage conditions.

For one file:

```powershell
python score.py import --source "D:\My recordings\Wanderer.flac" --track uw1_04 --assets assets
```

For the complete library, edit `import.csv` so each `source` is a path relative
to your recording folder, then:

```powershell
python score.py import-library --source "D:\My recordings" --assets assets
```

The default template expects `uw1_04.wav`, `uw2_14.wav`, etc. It includes optional
menu/credits assets too; individual imports can instead supply just the enabled
track IDs. FFmpeg is needed for MP3, FLAC, Ogg, stereo/float WAV, or resampling.
Find it through [the official FFmpeg download page](https://ffmpeg.org/download.html)
and pass `--ffmpeg "C:\Path\ffmpeg.exe"` if it is not on PATH. A 16-bit mono
PCM WAV at 22050, 44100 or 48000 Hz imports without FFmpeg.

## Render your own XMI files locally

The tested alternative uses **libADLMIDI 1.6.2.1** to render an offline FM
interpretation. It runs faster than real time and plays no audio through the
speakers. It is not an exact MT-32 emulation: use a properly made recording if
that timbre is important to you.

1. Obtain the renderer from the
   [libADLMIDI official releases](https://github.com/Wohlstand/libADLMIDI/releases/tag/v1.6.2.1).
   The tested Windows archive is `libADLMIDI-MinGW-w64-Release-x64.7z`;
   its SHA-256 is `c90743fb9c3806565429cd604c0baab6c413fbbfd9e82e8dc0f2ac6febf8a1f5`.
   Extract its whole folder so its DLL dependencies remain available.
2. Locate your own games' `SOUND` folders. For a CD/ISO edition, extract them
   locally with your archive utility. A GOG `game.gog` may be an ISO with both
   `UW/SOUND` and `UW2/SOUND`; not every edition has the same packaging.
3. Run:

```powershell
python score.py render-xmi --uw1-sound "D:\My UW1\SOUND" --uw2-sound "D:\My UW2\SOUND" --renderer "D:\libADLMIDI\bin\adlmidiplay.exe" --assets assets
```

The wrapper uses UW1 `UWxx.XMI` and UW2 `UWRxx.XMI`. Do not substitute the
AdLib-oriented AW/UWA files while keeping these renderer-bank choices. The
defaults are the renderer's FatMan MT32 bank 51 for UW1 and Underworld 2 bank 50
for UW2. It checks bank names before using those numbers. A custom WOPL file can
be passed through `--bank-uw1` or `--bank-uw2` if you prefer another instrument
set. These defaults are practical FM renditions, not proof of original-game
instrument fidelity. No instrument bank is copied into the release kit.

Rendering uses one chip, mono 16-bit PCM, no looping, and gain 0.5 before import
normalization. Private XMI copies, renderer logs and intermediate WAVs are kept
beside the asset library in a timestamped render folder. Each successful track
records source, renderer, bank/recipe and output checksums in
`xmi-provenance.json`. Rerunning skips intact completed tracks with the same
identity, and regenerates changed inputs. Originals remain untouched.

All 20 initial track candidates were rendered during development; the revised
default mapping uses 17, with optional menu/credits pieces retained in the
library. The six-second Fleeing cue was rejected for regional exploration.

## Build and install

Run the Underworld setup command from the README after the library is ready.
Do not use a test-pad library as if it were imported Ultima music. `setup`
creates a private fresh build, then installs it with a recovery journal.
Neither the local renderer nor its binaries are bundled here; there is no
runtime synth dependency once Arx-ready WAVs have been built.
