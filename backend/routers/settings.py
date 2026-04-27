from fastapi import APIRouter
from config import get_setting, set_setting
from models import SettingsResponse, SettingsUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])

@router.get("", response_model=SettingsResponse)
async def get_settings():
    return SettingsResponse(
        working_dir=await get_setting("working_dir"),
        ollama_endpoint=await get_setting("ollama_endpoint", "http://localhost:11434"),
        default_temperature=float(await get_setting("default_temperature", "0.3"))
    )

@router.put("", response_model=SettingsResponse)
async def update_settings(updates: SettingsUpdate):
    data = updates.model_dump()
    for key, value in data.items():
        if value is not None:
            await set_setting(key, str(value))
    return await get_settings()
