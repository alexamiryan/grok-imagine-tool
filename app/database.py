import aiosqlite
import sqlite3
from app.config import DB_PATH

_db: aiosqlite.Connection | None = None


async def init_db():
    global _db
    _db = await aiosqlite.connect(str(DB_PATH))
    _db.row_factory = sqlite3.Row
    await _db.execute("""
        CREATE TABLE IF NOT EXISTS generations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT UNIQUE NOT NULL,
            prompt TEXT NOT NULL,
            source_image TEXT,
            duration INTEGER NOT NULL,
            aspect_ratio TEXT NOT NULL,
            resolution TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            video_filename TEXT,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await _db.commit()


async def close_db():
    global _db
    if _db:
        await _db.close()
        _db = None


async def insert_generation(
    request_id: str,
    prompt: str,
    source_image: str | None,
    duration: int,
    aspect_ratio: str,
    resolution: str,
) -> int:
    cursor = await _db.execute(
        """INSERT INTO generations (request_id, prompt, source_image, duration, aspect_ratio, resolution)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (request_id, prompt, source_image, duration, aspect_ratio, resolution),
    )
    await _db.commit()
    return cursor.lastrowid


async def update_status(
    request_id: str,
    status: str,
    video_filename: str | None = None,
    error_message: str | None = None,
):
    await _db.execute(
        """UPDATE generations SET status = ?, video_filename = ?, error_message = ?
           WHERE request_id = ?""",
        (status, video_filename, error_message, request_id),
    )
    await _db.commit()


async def get_all_generations() -> list[dict]:
    cursor = await _db.execute(
        "SELECT * FROM generations ORDER BY created_at DESC"
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def get_generation(gen_id: int) -> dict | None:
    cursor = await _db.execute(
        "SELECT * FROM generations WHERE id = ?", (gen_id,)
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_pending_generations() -> list[dict]:
    cursor = await _db.execute(
        "SELECT * FROM generations WHERE status = 'pending'"
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]
