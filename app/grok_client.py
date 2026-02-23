import asyncio
import logging
import httpx
from app import config, database

logger = logging.getLogger(__name__)

client: httpx.AsyncClient | None = None


def create_client():
    global client
    client = httpx.AsyncClient(
        base_url=config.XAI_BASE_URL,
        headers={"Authorization": f"Bearer {config.XAI_API_KEY}"},
        timeout=60.0,
    )


async def close_client():
    global client
    if client:
        await client.aclose()
        client = None


async def submit_generation(
    prompt: str,
    image_data: str | None,
    duration: int,
    aspect_ratio: str,
    resolution: str,
) -> str:
    body = {
        "model": "grok-imagine-video",
        "prompt": prompt,
        "duration": duration,
        "resolution": resolution,
    }
    if aspect_ratio and aspect_ratio != "auto":
        body["aspect_ratio"] = aspect_ratio
    if image_data:
        body["image"] = {"url": image_data}

    logger.info("Submitting generation: prompt=%r, duration=%s, aspect_ratio=%s, resolution=%s, has_image=%s, body_keys=%s, image_url_len=%s",
                prompt[:80], duration, aspect_ratio, resolution, bool(image_data),
                list(body.keys()), len(body.get("image_url", "")) if "image_url" in body else 0)
    resp = await client.post("/videos/generations", json=body)
    logger.info("xAI API response: status=%s body=%s", resp.status_code, resp.text[:500])
    resp.raise_for_status()
    request_id = resp.json()["request_id"]
    logger.info("Generation submitted: request_id=%s", request_id)
    return request_id


async def poll_and_download(request_id: str):
    logger.info("Starting poll for request_id=%s", request_id)
    elapsed = 0
    while elapsed < config.MAX_POLL_DURATION_SECONDS:
        await asyncio.sleep(config.POLL_INTERVAL_SECONDS)
        elapsed += config.POLL_INTERVAL_SECONDS

        try:
            resp = await client.get(f"/videos/{request_id}")
            if resp.status_code == 400:
                error_body = resp.text
                logger.warning("Poll got 400 for %s (elapsed=%ds): %s", request_id, elapsed, error_body[:500])
                if "content moderation" in error_body.lower():
                    await database.update_status(
                        request_id, "rejected", error_message="Content moderation rejected"
                    )
                    return
                # Retry a few times — the API sometimes returns 400 transiently
                if elapsed < 30:
                    continue
                await database.update_status(
                    request_id, "failed", error_message=f"API error 400: {error_body[:200]}"
                )
                return
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("Poll request failed for %s: %s body=%s", request_id, e, e.response.text[:500])
            await database.update_status(
                request_id, "failed", error_message=f"{e}: {e.response.text[:200]}"
            )
            return
        except Exception as e:
            logger.error("Poll request failed for %s: %s", request_id, e)
            await database.update_status(
                request_id, "failed", error_message=str(e)
            )
            return

        status = data.get("status")
        has_video = "video" in data and data["video"] and data["video"].get("url")
        logger.debug("Poll %s: status=%s has_video=%s (elapsed=%ds)", request_id, status, bool(has_video), elapsed)

        if status == "pending" and not has_video:
            continue
        elif has_video or status == "done":
            video_url = data["video"]["url"]
            filename = f"{request_id}.mp4"
            filepath = config.VIDEOS_DIR / filename
            logger.info("Downloading video for %s from %s", request_id, video_url[:100])
            try:
                video_resp = await client.get(video_url, timeout=120.0)
                video_resp.raise_for_status()
                filepath.write_bytes(video_resp.content)
                logger.info("Video saved: %s (%d bytes)", filename, len(video_resp.content))
                await database.update_status(request_id, "done", filename)
            except Exception as e:
                logger.error("Video download failed for %s: %s", request_id, e)
                await database.update_status(
                    request_id, "failed", error_message=f"Download failed: {e}"
                )
            return
        elif status == "expired":
            logger.warning("Request %s expired", request_id)
            await database.update_status(
                request_id, "expired", error_message="Request expired"
            )
            return

    logger.error("Polling timeout for %s after %ds", request_id, elapsed)
    await database.update_status(
        request_id, "failed", error_message="Polling timeout exceeded"
    )
