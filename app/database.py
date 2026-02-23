import time
import aiosqlite
import sqlite3
from app.config import DB_PATH

_db: aiosqlite.Connection | None = None

# Cached count to avoid full table scan on every poll
_count_cache = {"value": 0, "expires": 0.0}
_COUNT_TTL = 5.0  # seconds


async def init_db():
    global _db
    _db = await aiosqlite.connect(str(DB_PATH))
    _db.row_factory = sqlite3.Row

    # Performance pragmas
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.execute("PRAGMA synchronous=NORMAL")
    await _db.execute("PRAGMA cache_size=-64000")
    await _db.execute("PRAGMA temp_store=MEMORY")

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
    await _db.execute("CREATE INDEX IF NOT EXISTS idx_gen_status ON generations(status)")
    await _db.execute("CREATE INDEX IF NOT EXISTS idx_gen_request_id ON generations(request_id)")
    await _db.execute("CREATE INDEX IF NOT EXISTS idx_gen_created_at ON generations(created_at DESC)")
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
    _count_cache["expires"] = 0.0  # invalidate count cache
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


_LIST_COLUMNS = (
    "id, request_id, prompt, "
    "CASE WHEN source_image IS NOT NULL THEN 1 ELSE 0 END AS has_source_image, "
    "duration, aspect_ratio, resolution, status, video_filename, error_message, created_at"
)

_DETAIL_COLUMNS = (
    "id, request_id, prompt, "
    "CASE WHEN source_image IS NOT NULL THEN 1 ELSE 0 END AS has_source_image, "
    "duration, aspect_ratio, resolution, status, video_filename, error_message, created_at"
)


async def get_all_generations(limit: int = 0, offset: int = 0) -> list[dict]:
    if limit > 0:
        cursor = await _db.execute(
            f"SELECT {_LIST_COLUMNS} FROM generations ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
    else:
        cursor = await _db.execute(
            f"SELECT {_LIST_COLUMNS} FROM generations ORDER BY created_at DESC"
        )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def get_generations_count() -> int:
    now = time.monotonic()
    if now < _count_cache["expires"]:
        return _count_cache["value"]
    cursor = await _db.execute("SELECT COUNT(*) FROM generations")
    row = await cursor.fetchone()
    _count_cache["value"] = row[0]
    _count_cache["expires"] = now + _COUNT_TTL
    return row[0]


async def get_generation(gen_id: int) -> dict | None:
    cursor = await _db.execute(
        f"SELECT {_DETAIL_COLUMNS} FROM generations WHERE id = ?", (gen_id,)
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_generation_image(gen_id: int) -> str | None:
    """Fetch only the source_image blob for a generation."""
    cursor = await _db.execute(
        "SELECT source_image FROM generations WHERE id = ?", (gen_id,)
    )
    row = await cursor.fetchone()
    return row[0] if row else None


async def get_pending_generations() -> list[dict]:
    cursor = await _db.execute(
        "SELECT request_id FROM generations WHERE status = 'pending'"
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]
