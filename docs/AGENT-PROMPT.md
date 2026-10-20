# Prompt: let an agent fetch the Ultima music for you

Copy the block below into a coding agent that can run commands on your PC
(Claude Code, Codex, Hermes, Cursor, ...). Start it in this kit's folder. It will
look for your own Ultima Underworld I and II first and render the music from the
games' files. Only if that fails, and only after asking you, does it fall back to
downloading the soundtracks from YouTube for your personal use.

Read this before using the YouTube route: downloading from YouTube is against
YouTube's terms of service, and the music remains copyrighted. Owning the games
does not make it free to share. Keep whatever you download on your own machine,
and never redistribute it, this kit's built audio included. If in doubt, use the
local route.

```text
You are helping me install the "Arx Underworld Music" mod for Arx Fatalis / Arx
Libertatis. The current folder is the mod kit. Your job: fill an `assets` folder
with the Ultima Underworld I/II soundtrack, then install the mod with it.

Ground rules
- Read README.md, docs/IMPORT.md, tracks.csv, import.csv and mapping.csv first.
  The rows of mapping.csv with enabled=1 name the track IDs that are required.
  Supply all 20 IDs in tracks.csv if you can; the required ones are a must.
- Do not edit the kit's code, mapping.csv, mix.json or combat.json.
- Do not launch Arx or either Ultima game, and do not open game windows.
- Ask me before installing or downloading any program (FFmpeg, libADLMIDI,
  yt-dlp, 7-Zip) and before any download of music.
- Keep all audio you obtain, and every intermediate file, inside this kit's
  `.work/` and `assets/` folders. Both are git-ignored. Never commit, upload or
  share them.
- Ask me for the Arx game folder (the one containing SFX.pak) when you need it.

Route A, preferred: my own copies of the games
1. Search this PC for Ultima Underworld I and II. Likely places: GOG folders
   (C:\GOG Games, C:\Program Files (x86)\GOG Galaxy\Games), Steam libraries,
   DOSBox folders, and extracted CD/ISO images. UW1 has SOUND\UW01.XMI and
   similar; UW2 has SOUND\UWR01.XMI and similar. A GOG `game.gog` file can be an
   ISO image holding UW\SOUND and UW2\SOUND; extract a copy into
   .work\ultima-sound\ (never modify the originals). Show me what you found.
2. If both SOUND folders are there, follow "Render your own XMI files locally"
   in docs/IMPORT.md exactly: fetch the named libADLMIDI release (after asking),
   check its SHA-256 against the value in that file, then run
   `python score.py render-xmi ... --assets assets`.
3. Then go to "Install" below.

Route B, fallback: YouTube, for my personal use only
Only if Route A found nothing usable, and only after I say yes.
1. With yt-dlp and FFmpeg, find one recording per track ID in tracks.csv,
   searching by game and track title (for example "Ultima Underworld Wanderer").
   Use ONE consistent rendition for each game: all Roland MT-32, or all Sound
   Blaster/AdLib. Do not mix them, and skip remixes, covers and "remastered"
   versions unless I ask for them. A single channel's full-soundtrack upload is
   usually the most consistent source.
2. Reject videos with gameplay sound, speech, narration or intros mixed in.
3. Download audio only, into .work\youtube\, one file per track, named after the
   import_filename column of tracks.csv (uw1_04, uw2_14, ...). If the source is
   one long compilation video, split it at its chapter marks (yt-dlp
   --split-chapters) or at the timestamps in its description, and confirm every
   piece is the right track and length.
4. Trim silence at the START of each file (ffmpeg silenceremove, start only):
   every cue starts at the beginning of its track, and uw2_10 plays only its
   first 24 seconds, so a lead-in of silence makes the music start late or not
   at all. Leave the end alone unless there is a long silent tail.
5. Write .work\youtube\SOURCES.md listing the URL, uploader and timestamps used
   for every track ID, so the set can be rebuilt later.

Check the audio (both routes)
The kit's build normalises every track to the same loudness (-20 LUFS, -1 dBFS
peak limiter, see mix.json), so different volumes between sources even out by
themselves. What normalisation cannot fix, and what you must check:
- Measure every file (ffmpeg -af ebur128 or loudnorm print_format=summary): report
  integrated loudness, loudness range and true peak per track.
- Flag tracks that are clipped (true peak at or above 0 dBFS with audible
  distortion), much quieter or louder than the rest (more than about 6 LU from
  the median), very dynamic (a quiet intro before a loud body sounds too quiet in
  game), or that start with more than a second of silence.
- Listen to nothing yourself and do not guess: show me the table and the flagged
  tracks, and let me decide whether to replace them.

Install
1. Put the files in one folder and edit import.csv so each `source` is the file
   name for its track ID (for example uw1_04.flac). Every row must point to an
   existing file: delete the rows of optional tracks you could not get, but keep
   every track that mapping.csv enables. Then run
   `python score.py import-library --source <that folder> --assets assets`
   (add `--ffmpeg <path>` if FFmpeg is not on PATH).
2. If the test version of the mod is installed, uninstall it first:
   `python score.py uninstall --game-dir "<Arx folder>"`.
3. Install: `python score.py setup --game-dir "<Arx folder>" --mode underworld --assets assets`.
4. Report what you did: route used, one row per track (source, duration, loudness,
   flags), and the install result. Then tell me to start Arx myself to listen. If
   the music is too loud or quiet against the game's sounds, the README explains
   the `gain` column and `--gain-scale`.
```
