# Changelog

What changed in each version of the Clickwheel local edition. The page footer shows the version you run. From 1.2.2 on, every version is also a GitHub release with source archives.

## 1.2.2 - 2026-10-14

- When YouTube refuses a stream (HTTP 403, a 5xx error, a timeout or a dropped connection), Clickwheel retries up to three times with fresh links and shows "Retrying (2 of 3)" while it waits. Cancel still works during the pause.
- After three refusals the message reads YOUTUBE REFUSED THE STREAM. Wait a minute, then press Retry.

## 1.2.1 - 2026-10-14

- A busy port no longer stops the app. It moves to the next free port (8766, 8767, …) and the log says which.
- Each running copy keeps its jobs in its own folder, so a second copy no longer clears the first one's files.

## 1.2.0 - 2026-10-14

- First public version: AAC 256 or ALAC lossless at 44.1 kHz, every chapter of a mix as its own track, and iPod tags and cover art.
- No accounts. The app only listens on this computer.
