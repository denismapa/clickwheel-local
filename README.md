# Clickwheel · local edition

**One link in. A tagged album out.**

Clickwheel turns a YouTube link into iPod-ready audio. You get high-fidelity AAC or ALAC with tags and cover art, and every chapter of a mix comes out as its own track. It runs on your own computer and saves the file straight to your browser's downloads.

This edition has no accounts and no sign-in. It therefore only listens on `127.0.0.1` and refuses to start on a network address, so nobody else on your network can reach it.

## What you get

| | AAC 256 (default) | ALAC |
|---|---|---|
| Codec | AAC-LC at 256 kbps. Apple's AudioToolbox encoder on a Mac (the iTunes Plus spec), ffmpeg's built-in encoder elsewhere | Apple Lossless, 16-bit |
| Sample rate | 44.1 kHz | 44.1 kHz |
| Size | about 1.9 MB per minute | about 5.4 MB per minute |
| File | `.m4a` (ffmpeg `ipod` muxer, faststart) | `.m4a` |

Every file also carries:

- A 600×600 baseline JPEG cover. Older iPods skip progressive JPEGs.
- Title, artist, album artist, album, year, track n/N, disc, genre, media kind Music, and the source URL as the comment.
- For split mixes, the compilation and gapless-album flags, so the iPod keeps the mix together.
- Text without emoji, with fullwidth letters folded to plain ones. iPod fonts have no emoji.

## Why these choices

- YouTube's best audio is usually Opus at about 140 kbps and 48 kHz. Its AAC stream is lower in bitrate and cut off near 16 kHz. Clickwheel takes the Opus stream and encodes it once at 256 kbps, which keeps the high band.
- 44.1 kHz is the iPod's native rate, so the iPod never resamples. Clickwheel resamples with a 64-tap filter and TPDF dither to 16-bit.
- If the best stream is already AAC-LC at 44.1 kHz, it is copied untouched, because re-encoding AAC to AAC only loses quality.
- YouTube audio is lossy at the source. ALAC keeps exactly what YouTube sent with no further loss, but it cannot restore what was never there.

## Requirements

- Python 3.12 or newer, [FFmpeg](https://ffmpeg.org) and [Deno](https://deno.com). Deno is the JavaScript runtime yt-dlp needs for YouTube.
- macOS with [Homebrew](https://brew.sh):

  ```bash
  brew install python ffmpeg deno
  ```

- Linux: install `python3`, `python3-venv` and `ffmpeg` from your package manager, and Deno from deno.com.

## Run

```bash
./run.sh
```

The first run builds `.venv` and installs the pinned dependencies. Then the app opens at http://localhost:8765. If that port is taken, it uses the next free one (8766, 8767, …) and the log says which.

## Use

1. Paste a YouTube link: a video, a mix, `youtu.be`, Shorts or `music.youtube.com`. Clickwheel reads it and shows the duration, track list, source format and a size estimate.
2. Pick **AAC 256** or **ALAC lossless**, and turn **Split chapters** on or off.
3. Press **Download**. When it finishes, the browser saves either one `.m4a` or, for a split mix, a `.zip` holding one album folder of `NN Artist - Title.m4a` tracks.
4. Finished files stay available for 60 minutes, then the server deletes them.

## Put it on the iPod

1. Unzip the mix. Drag the folder, or the `.m4a`, into Music on macOS (iTunes on Windows).
2. Connect the iPod and sync music.

## Configure

Copy `.env.example` to `.env`; `run.sh` reads it. Every value is optional.

| Variable | Default | Meaning |
|---|---|---|
| `CLICKWHEEL_PORT` | `8765` | Port on 127.0.0.1; if it is taken, the next free one is used |
| `CLICKWHEEL_WORK_DIR` | `<system temp>/clickwheel` | Where jobs are processed, in a `port-<n>` folder per running copy |
| `CLICKWHEEL_MAX_JOBS` | `2` | Jobs running at once |
| `CLICKWHEEL_ENCODE_WORKERS` | `4` | Parallel track encodes per job |
| `CLICKWHEEL_MAX_DURATION_MIN` | `720` | Longest video accepted |
| `CLICKWHEEL_FILE_TTL_MIN` | `60` | Minutes a finished file stays downloadable |
| `CLICKWHEEL_GENRE` | `Lo-Fi` | Genre tag; empty for none |
| `CLICKWHEEL_OPEN_BROWSER` | `1` | Open the browser on start |

## Limits

- One video or mix per link. Playlists, live streams, members-only and age-restricted videos are refused with a clear message.
- 12 hours maximum by default.

## Tests

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

Tests that hit real YouTube are opt-in:

```bash
CLICKWHEEL_LIVE=1 .venv/bin/python -m pytest -m live
```

## Troubleshooting

| Message | Fix |
|---|---|
| `SOURCE REFUSED.` on every link | YouTube changed. Update the `yt-dlp[default]` pin in `requirements.txt` to the latest release, then `./run.sh` |
| `NO JAVASCRIPT RUNTIME.` | Install Deno |
| `YOUTUBE BLOCKED THE REQUEST.` | YouTube is rate-limiting your network. Wait a few minutes |
| `YOUTUBE REFUSED THE STREAM.` | YouTube refused the download three times in a row (Clickwheel retries on its own first). Wait a minute, then press Retry |
| `Clickwheel needs the '…' package` | Start it with `./run.sh`, which uses the project's `.venv` |

## Privacy

- **No outside resources:** the page loads nothing from other sites, and its content security policy allows only the app itself plus YouTube's thumbnail host.
- **Only YouTube:** the server talks only to YouTube, through yt-dlp, for the links you paste.
- **Short-lived files:** files are processed in a temporary folder and deleted after an hour.

## Legal

Clickwheel is for personal use. Download only what you have the right to keep, respect YouTube's terms and the law where you live, and support the artists you listen to.

## License

Copyright (C) 2026 the Clickwheel authors.

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version. See [LICENSE](LICENSE).

Clickwheel builds on these projects:

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) (Unlicense)
- [FFmpeg](https://ffmpeg.org) (LGPL/GPL, installed separately)
- [FastAPI](https://fastapi.tiangolo.com) (MIT)
- [mutagen](https://github.com/quodlibet/mutagen) (GPL-2.0-or-later)
