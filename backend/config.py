import json
import aiosqlite
from database import DB_PATH

async def get_setting(key: str, default: str = "") -> str:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    row = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
    result = await row.fetchone()
    await db.close()
    return result["value"] if result else default

async def set_setting(key: str, value: str):
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = ?",
        (key, value, value)
    )
    await db.commit()
    await db.close()
