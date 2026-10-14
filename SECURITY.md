# Security

## Design

The local edition has no accounts, so it is built to stay on the computer it runs on:

- **Local only.** It listens on `127.0.0.1` or `localhost` only, and refuses to start on any other address.
- **DNS rebinding.** Requests whose `Host` header is not allow-listed are refused.
- **Cross-site requests.** Writes need an exact same-origin `Origin` and a JSON body. Bodies over 64 KB are refused.
- **Content security policy.** A strict CSP allows no inline scripts, no third-party scripts, styles or fonts, and no framing.
- **YouTube only.** Links are reduced to `https://www.youtube.com/watch?v=<id>` before yt-dlp sees them, and yt-dlp runs with only its YouTube extractor.
- **No shell.** ffmpeg runs from argument lists, never through a shell.
- **Temporary files.** Files are written to a temporary folder and deleted after an hour.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting on this repository: **Security → Report a vulnerability**. Don't open a public issue. You will get a reply within a week.
