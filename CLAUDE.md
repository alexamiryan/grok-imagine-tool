# CLAUDE.md

## Project Overview

Dockerized web app for video generation using xAI Grok Imagine 1.0 API. FastAPI backend, vanilla JS frontend, SQLite database.

## Running

```
docker-compose up --build
```

App runs on http://localhost:8000. Data (DB + videos) persists in `./data/` volume mount.

## Key API Gotchas

- **Image field**: REST API requires `"image": {"url": "data:image/...;base64,..."}` (nested object). NOT `"image_url"` (that's the Python SDK parameter name — the REST API silently ignores it).
- **Poll response**: When video is done, the API returns `{"video": {"url": "..."}}` WITHOUT a `"status"` field. Only pending responses include `"status": "pending"`. Always check for video presence, not just status.
- **Aspect ratio "auto"**: Omit the `aspect_ratio` field entirely from the request body. Don't send `"auto"` as a value.
- **Content moderation**: API returns HTTP 400 with "Generated video rejected by content moderation" in body. Handle as a distinct "rejected" status, not a generic error.
- **Transient 400s**: The poll endpoint sometimes returns 400 during early polling. Retry for up to 30 seconds before treating as a real failure.

## API Endpoints

- `POST https://api.x.ai/v1/videos/generations` — submit generation
- `GET https://api.x.ai/v1/videos/{request_id}` — poll status
- `GET https://management-api.x.ai/v1/billing/teams/{team_id}/postpaid/invoice/preview` — balance (uses separate management key)

## Architecture Notes

- Background polling uses `asyncio.create_task` with `_task_done_callback` for error logging
- On startup, pending DB rows resume polling automatically
- Frontend uses diff-based DOM updates (compares generation IDs and statuses) to avoid flickering during poll refreshes
- Source images stored as base64 in SQLite (simple, no file management needed)
- Videos downloaded to `/data/videos/{request_id}.mp4` immediately on completion (xAI video URLs are ephemeral)

## File Guide

| File | Purpose |
|---|---|
| `app/main.py` | FastAPI app, routes, lifespan handler |
| `app/config.py` | Env vars, paths, poll settings |
| `app/database.py` | SQLite schema + async CRUD |
| `app/grok_client.py` | xAI API: submit + poll + download |
| `app/models.py` | Pydantic request models (GenerateRequest) |
| `app/static/index.html` | Two-column SPA layout |
| `app/static/style.css` | Dark theme styles |
| `app/static/app.js` | Frontend logic (upload, submit, history, polling) |

## Common Issues

- **CSS `hidden` attribute ignored**: If an element has `display: flex` in CSS, the HTML `hidden` attribute won't work. Add explicit `[hidden] { display: none; }` rule.
- **Videos flicker on refresh**: Don't replace DOM nodes with innerHTML on every poll. Use diff-based updates that reuse existing nodes when status hasn't changed.
