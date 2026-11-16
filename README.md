# YT Downloader

A dark-themed desktop app for downloading videos and audio using [yt-dlp](https://github.com/yt-dlp/yt-dlp), built with Python and Tkinter.

![App Screenshot](screenshot.png)

## Features

* **Multi-URL Queue:** Paste multiple video or playlist URLs (one per line) and download them one after another.
* **Quality & Audio Selection:** Download up to 4K (`2160p`), standard resolutions (`1080p`, `720p`, etc.), or extract audio-only (`MP3` / `M4A`).
* **Large-File Friendly:** Resumes interrupted downloads automatically and checks available disk space before starting.
* **Browser Cookie Sign-In:** Access age-restricted, members-only, or private videos using your browser's logged-in session—no Google password is ever entered or stored in the app.
* **Polite Client Controls:** Adjustable speed cap (MiB/s), random delays between videos, and optional proxy support to avoid rate limits.

## Quick Start

### 1. Download the App
* **[Click here to download `yt_downloader.py`](https://github.com/<your-username>/<your-repo-name>/releases/latest/download/yt_downloader.py)** *(or right-click the link and choose **Save Link As...**)*

### 2. Install Requirements
Make sure you have **Python 3.9+** installed, then open a terminal / command prompt and run:
```bash
pip install yt-dlp
