from fastapi import APIRouter, HTTPException
import httpx
from config import get_setting

router = APIRouter(prefix="/api/ollama", tags=["ollama"])

@router.get("/models")
async def list_ollama_models():
    endpoint = await get_setting("ollama_endpoint", "http://localhost:11435")
    api_key = await get_setting("ollama_api_key", "")
    url = f"{endpoint.rstrip('/')}/api/tags"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            models = data.get("models", [])
            return [
                {
                    "name": m.get("name", m.get("model", "unknown")),
                    "size": m.get("size", 0),
                    "digest": m.get("digest", "")[:16],
                    "modified_at": m.get("modified_at", ""),
                }
                for m in models
            ]
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Cannot reach Ollama at {endpoint}: {e}")
    except Exception as e:
        raise HTTPException(500, f"Error fetching models: {e}")
