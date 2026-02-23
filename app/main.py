import asyncio
import base64
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app import config, database, grok_client
from app.models import GenerateRequest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

_mgmt_client: httpx.AsyncClient | None = None


def _task_done_callback(task: asyncio.Task):
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        logger.error("Background task failed: %s", exc, exc_info=exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _mgmt_client

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    await database.init_db()
    grok_client.create_client()

    if config.XAI_MANAGEMENT_KEY:
        _mgmt_client = httpx.AsyncClient(
            base_url=config.XAI_MANAGEMENT_BASE_URL,
            headers={"Authorization": f"Bearer {config.XAI_MANAGEMENT_KEY}"},
            timeout=10.0,
        )

    pending = await database.get_pending_generations()
    for gen in pending:
        task = asyncio.create_task(grok_client.poll_and_download(gen["request_id"]))
        task.add_done_callback(_task_done_callback)

    yield

    await grok_client.close_client()
    if _mgmt_client:
        await _mgmt_client.aclose()
        _mgmt_client = None
    await database.close_db()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def index():
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Cache-Control": "no-cache"},
    )


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.post("/api/generate")
async def generate(req: GenerateRequest):
    logger.info("Generate request: prompt=%r, has_image=%s, duration=%s, aspect_ratio=%s, resolution=%s",
                req.prompt[:80], req.image_data is not None,
                req.duration, req.aspect_ratio.value, req.resolution.value)
    try:
        request_id = await grok_client.submit_generation(
            req.prompt,
            req.image_data,
            req.duration,
            req.aspect_ratio.value,
            req.resolution.value,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"xAI API error: {e}")

    row_id = await database.insert_generation(
        request_id,
        req.prompt,
        req.image_data,
        req.duration,
        req.aspect_ratio.value,
        req.resolution.value,
    )

    task = asyncio.create_task(grok_client.poll_and_download(request_id))
    task.add_done_callback(_task_done_callback)

    return {"id": row_id, "request_id": request_id}


@app.get("/api/generations")
async def list_generations(limit: int = 0, offset: int = 0):
    rows = await database.get_all_generations(limit=limit, offset=offset)
    total = await database.get_generations_count()
    return {"items": rows, "total": total}


@app.get("/api/generations/{gen_id}")
async def get_generation(gen_id: int):
    row = await database.get_generation(gen_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return row


@app.get("/api/generations/{gen_id}/image")
async def get_generation_image(gen_id: int):
    data_uri = await database.get_generation_image(gen_id)
    if not data_uri:
        raise HTTPException(status_code=404, detail="Image not found")
    header, b64data = data_uri.split(",", 1)
    media_type = header.split(":")[1].split(";")[0]
    image_bytes = base64.b64decode(b64data)
    return Response(content=image_bytes, media_type=media_type)


@app.get("/api/balance")
async def get_balance():
    if not _mgmt_client or not config.XAI_TEAM_ID:
        return {"error": "Management key or team ID not configured"}
    try:
        resp = await _mgmt_client.get(
            f"/v1/billing/teams/{config.XAI_TEAM_ID}/postpaid/invoice/preview"
        )
        resp.raise_for_status()
        data = resp.json()
        invoice = data.get("coreInvoice", {})
        prepaid_cents = abs(int(invoice.get("prepaidCredits", {}).get("val", "0")))
        used_cents = abs(int(invoice.get("prepaidCreditsUsed", {}).get("val", "0")))
        remaining_cents = max(0, prepaid_cents - used_cents)
        invoice_cents = int(invoice.get("amountAfterVat", "0"))
        total_cents = int(invoice.get("totalWithCorr", {}).get("val", "0"))
        return {
            "prepaid": prepaid_cents,
            "used": used_cents,
            "remaining": remaining_cents,
            "invoice": invoice_cents,
            "total": total_cents,
        }
    except Exception as e:
        logger.error("Failed to fetch balance: %s", e)
        return {"error": str(e)}


@app.get("/api/videos/{filename}")
async def serve_video(filename: str, request: Request):
    path = config.VIDEOS_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Video not found")

    file_size = path.stat().st_size
    range_header = request.headers.get("range")

    if range_header:
        # Parse "bytes=start-end"
        range_spec = range_header.replace("bytes=", "")
        parts = range_spec.split("-")
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if parts[1] else file_size - 1
        end = min(end, file_size - 1)
        length = end - start + 1

        def iter_range():
            with open(path, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(8192, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(
            iter_range(),
            status_code=206,
            media_type="video/mp4",
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Content-Length": str(length),
                "Accept-Ranges": "bytes",
            },
        )

    return FileResponse(
        str(path),
        media_type="video/mp4",
        headers={"Accept-Ranges": "bytes"},
    )
