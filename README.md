# Youtube-Downloader-yt-dlp-
A simple app for downloading videos off of youtube for free.

![App Screenshot](assets/screenshot.png)

## Features

* **Multi-URL Queue:** Paste multiple video or playlist URLs (one per line) and download them sequentially.
* **Quality & Audio Selection:** Download up to 4K (`2160p`), standard resolutions (`1080p`, `720p`, etc.), or extract audio-only (`MP3` / `M4A`).
* **Large-File Friendly:** Supports resumable `.part` downloads, chunked HTTP requests, fragment retries with exponential backoff, and pre-download disk-space checks.
* **Browser Cookie Sign-In:** Access age-restricted, members-only, or private videos via your browser's active session or an exported `cookies.txt`—no Google password is ever entered or stored in the app.
* **Polite Client Controls:** Configurable speed cap (MiB/s), randomized delays between items, parallel fragment limits, and optional HTTP/SOCKS5 proxy support.

## Prerequisites

1. **Python 3.9+**
   * *Linux users:* Ensure Tkinter is installed (e.g., `sudo apt install python3-tk`).
2. **[FFmpeg](https://ffmpeg.org/download.html)** *(Recommended)*
   * Required on your system `PATH` to merge high-resolution (1080p+) video and audio streams and to extract MP3 audio.
   * **Windows:** `winget install Gyan.FFmpeg`
   * **macOS:** `brew install ffmpeg`
   * **Linux (Ubuntu/Debian):** `sudo apt install ffmpeg`

## Installation & Usage

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/](https://github.com/)<your-username>/<your-repo-name>.git
   cd <your-repo-name>
