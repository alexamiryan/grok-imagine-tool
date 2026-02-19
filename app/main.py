import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import config, database, grok_client
from app.models import GenerateRequest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


def _task_done_callback(task: asyncio.Task):
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        logger.error("Background task failed: %s", exc, exc_info=exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    await database.init_db()
    grok_client.create_client()

    pending = await database.get_pending_generations()
    for gen in pending:
        task = asyncio.create_task(grok_client.poll_and_download(gen["request_id"]))
        task.add_done_callback(_task_done_callback)

    yield

    await grok_client.close_client()
    await database.close_db()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.post("/api/generate")
async def generate(req: GenerateRequest):
    logger.info("Generate request: prompt=%r, has_image=%s, image_size=%s, duration=%s, aspect_ratio=%s, resolution=%s",
                req.prompt[:80], req.image_data is not None,
                len(req.image_data) if req.image_data else 0,
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
async def list_generations():
    rows = await database.get_all_generations()
    return rows


@app.get("/api/generations/{gen_id}")
async def get_generation(gen_id: int):
    row = await database.get_generation(gen_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return row


@app.get("/api/balance")
async def get_balance():
    if not config.XAI_MANAGEMENT_KEY or not config.XAI_TEAM_ID:
        return {"error": "Management key or team ID not configured"}
    try:
        import httpx
        async with httpx.AsyncClient(
            base_url=config.XAI_MANAGEMENT_BASE_URL,
            headers={"Authorization": f"Bearer {config.XAI_MANAGEMENT_KEY}"},
            timeout=10.0,
        ) as mgmt_client:
            resp = await mgmt_client.get(
                f"/v1/billing/teams/{config.XAI_TEAM_ID}/postpaid/invoice/preview"
            )
            resp.raise_for_status()
            data = resp.json()
            invoice = data.get("coreInvoice", {})
            prepaid_cents = abs(int(invoice.get("prepaidCredits", {}).get("val", "0")))
            used_cents = abs(int(invoice.get("prepaidCreditsUsed", {}).get("val", "0")))
            remaining_cents = prepaid_cents - used_cents
            return {
                "prepaid": prepaid_cents,
                "used": used_cents,
                "remaining": remaining_cents,
            }
    except Exception as e:
        logger.error("Failed to fetch balance: %s", e)
        return {"error": str(e)}


@app.get("/api/videos/{filename}")
async def serve_video(filename: str):
    path = config.VIDEOS_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(str(path), media_type="video/mp4")
