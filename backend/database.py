import aiosqlite

DB_PATH = "data/app.db"

async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()

async def init_db():
    import os
    os.makedirs("data", exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('planner','coder','tester')),
            model_name TEXT NOT NULL,
            system_prompt TEXT NOT NULL,
            temperature REAL DEFAULT 0.3,
            ollama_endpoint TEXT DEFAULT 'http://localhost:11435',
            api_key TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            planner_agent_id INTEGER REFERENCES agents(id),
            coder_agent_id INTEGER REFERENCES agents(id),
            tester_agent_id INTEGER REFERENCES agents(id),
            agent_overrides TEXT DEFAULT '{}',
            loop_mode TEXT DEFAULT 'automatic' CHECK(loop_mode IN ('automatic','manual')),
            max_iterations INTEGER DEFAULT 5,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER REFERENCES jobs(id),
            status TEXT DEFAULT 'pending',
            feature_request TEXT NOT NULL,
            context TEXT DEFAULT '{}',
            iterations INTEGER DEFAULT 0,
            roadmap TEXT DEFAULT NULL,
            coder_outputs TEXT DEFAULT '[]',
            test_reports TEXT DEFAULT '[]',
            human_requests TEXT DEFAULT '[]',
            started_at TEXT DEFAULT (datetime('now')),
            completed_at TEXT DEFAULT NULL
        );
        CREATE TABLE IF NOT EXISTS run_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER REFERENCES runs(id),
            phase TEXT NOT NULL,
            agent TEXT,
            input TEXT,
            output TEXT,
            latency_ms INTEGER,
            error TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        INSERT OR IGNORE INTO settings (key, value) VALUES ('working_dir', '');
        INSERT OR IGNORE INTO settings (key, value) VALUES ('ollama_endpoint', 'http://localhost:11435');
        INSERT OR IGNORE INTO settings (key, value) VALUES ('ollama_api_key', '');
        INSERT OR IGNORE INTO settings (key, value) VALUES ('default_temperature', '0.3');
    """)
    await db.commit()
    await db.close()
