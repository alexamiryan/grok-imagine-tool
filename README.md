# Grok Imagine Video Generator

Web app for generating videos using the xAI Grok Imagine 1.0 API (`grok-imagine-video` model). Supports text-to-video and image-to-video generation.

## Features

- Text-to-video and image-to-video generation
- Drag-and-drop image upload
- Configurable duration (1–15s), aspect ratio, and resolution (480p/720p)
- Generation history with inline video playback and download
- Click-to-reuse prompts and source images from history
- Real-time credit balance display
- Auto-resumes pending generations on restart

## Quick Start

1. Copy `.env.example` to `.env` and fill in your keys:
   ```
   cp .env.example .env
   ```

2. Start the app:
   ```
   docker-compose up --build
   ```

3. Open http://localhost:8000

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `XAI_API_KEY` | Yes | xAI API key for Grok Imagine |
| `XAI_MANAGEMENT_KEY` | No | xAI Management API key (for balance display) |
| `XAI_TEAM_ID` | No | xAI team ID (for balance display) |

## Architecture

- **Backend**: FastAPI (Python 3.12) with async polling via `asyncio.create_task`
- **Frontend**: Vanilla HTML/CSS/JS — no build step
- **Database**: SQLite via `aiosqlite` — persisted in `data/` volume
- **Videos**: Downloaded to `data/videos/` on generation completion

### Project Structure

```
app/
├── main.py          # FastAPI routes and lifespan
├── config.py        # Environment variables and paths
├── database.py      # SQLite schema and CRUD
├── grok_client.py   # xAI API client (submit, poll, download)
├── models.py        # Pydantic request models
└── static/
    ├── index.html   # Two-column SPA
    ├── style.css    # Dark theme
    └── app.js       # Upload, submit, history polling
```

## Pricing

Grok Imagine Video: $0.05/second flat rate regardless of resolution.
