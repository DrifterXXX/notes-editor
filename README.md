# Notes Editor v3.0

A lightweight Markdown online editor with split-screen live preview. Browse, edit, and manage Markdown files through a clean web interface.

## Features

- **Split-Screen Preview** — Real-time Markdown rendering alongside editor
- **File Browser** — Navigate and manage Markdown files
- **Auto-Save** — Automatic saving with visual feedback
- **Cookie-based Auth** — Simple authentication system
- **Markdown Support** — Full CommonMark + GitHub Flavored Markdown

## Quick Start

```bash
cd notes-editor
python3 server.py
```

Open `http://localhost:8080` in your browser.

## Authentication

Credentials are managed via `~/.shell-server/config.json`. A fallback token is generated using `secrets.token_urlsafe()` if no config is found. Password verification uses SHA-256 hashing with constant-time comparison.

## Tech Stack

- Python 3 `http.server`
- Pure CSS/JavaScript frontend
- Markdown-to-HTML rendering

## License

MIT
