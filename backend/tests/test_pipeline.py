import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import aiosqlite

from orchestrator import Orchestrator


async def _setup_db(db_path: str):
    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row
    await db.executescript(
        """
        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY,
            name TEXT,
            role TEXT,
            model_name TEXT,
            system_prompt TEXT,
            temperature REAL,
            ollama_endpoint TEXT,
            api_key TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY,
            name TEXT,
            description TEXT,
            planner_agent_id INTEGER,
            coder_agent_id INTEGER,
            tester_agent_id INTEGER,
            agent_overrides TEXT,
            loop_mode TEXT,
            max_iterations INTEGER,
            definition_of_done TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY,
            job_id INTEGER,
            status TEXT,
            feature_request TEXT,
            context TEXT,
            iterations INTEGER DEFAULT 0,
            roadmap TEXT,
            coder_outputs TEXT,
            test_reports TEXT,
            human_requests TEXT,
            started_at TEXT,
            completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS run_steps (
            id INTEGER PRIMARY KEY,
            run_id INTEGER,
            step_number INTEGER,
            step_type TEXT,
            phase TEXT,
            agent TEXT,
            input TEXT,
            output TEXT,
            latency_ms INTEGER,
            error TEXT,
            files_changed TEXT,
            git_commit TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """
    )
    await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('working_dir', '')")
    await db.execute(
        "INSERT INTO agents (id, name, role, model_name, system_prompt, temperature, ollama_endpoint, api_key) "
        "VALUES (1, 'Planner', 'planner', 'gpt-4', 'Planner prompt', 0.3, '', '')"
    )
    await db.execute(
        "INSERT INTO agents (id, name, role, model_name, system_prompt, temperature, ollama_endpoint, api_key) "
        "VALUES (2, 'Coder', 'coder', 'gpt-4', 'Coder prompt', 0.3, '', '')"
    )
    await db.execute(
        "INSERT INTO agents (id, name, role, model_name, system_prompt, temperature, ollama_endpoint, api_key) "
        "VALUES (3, 'Tester', 'tester', 'gpt-4', 'Tester prompt', 0.3, '', '')"
    )
    await db.execute(
        "INSERT INTO jobs (id, name, planner_agent_id, coder_agent_id, tester_agent_id, agent_overrides, loop_mode, max_iterations, definition_of_done) "
        "VALUES (1, 'Test Job', 1, 2, 3, '{}', 'automatic', 3, 'Build a greeting endpoint')"
    )
    await db.execute(
        "INSERT INTO runs (id, job_id, status, feature_request) "
        "VALUES (42, 1, 'pending', 'Build a greeting endpoint')"
    )
    await db.commit()
    await db.close()


def test_sequential_pipeline():
    """Integration test for the sequential multi-agent pipeline."""
    job = {
        "id": 1,
        "planner_agent_id": 1,
        "coder_agent_id": 2,
        "tester_agent_id": 3,
        "agent_overrides": "{}",
        "max_iterations": 3,
        "definition_of_done": "Build a greeting endpoint that returns 'hello'",
    }

    def mock_run(prompt, system_prompt=None):
        p_str = str(prompt)
        # Planner evaluation prompt contains serialized plan/code/test
        if '"plan"' in p_str and '"code"' in p_str:
            return {
                "output": {"action": "done", "roadmap": "Complete"},
                "files_changed": [],
            }
        sp = str(system_prompt or "")
        if "PLANNER" in sp.upper():
            return {
                "output": {"action": "continue", "next_task": "Implement greeting"},
                "files_changed": [],
            }
        if "CODER" in sp.upper():
            return {
                "output": {"files_changed": ["app.py"]},
                "files_changed": ["app.py"],
            }
        if "TESTER" in sp.upper():
            return {
                "output": {"summary": "Tests passed"},
                "files_changed": [],
            }
        return {"output": {}, "files_changed": []}

    async def _run():
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            await _setup_db(db_path)

            with patch("orchestrator.DB_PATH", db_path):
                with patch("shutil.which", return_value=True):
                    with patch("orchestrator.WorktreeManager") as MockWM:
                        wm_instance = MagicMock()
                        wm_instance.create.return_value = tmpdir
                        wm_instance.worktree_path = Path(tmpdir)
                        wm_instance.read_file.return_value = ""
                        wm_instance.commit.return_value = True
                        MockWM.return_value = wm_instance

                        with patch("orchestrator.OpenCodeAgentRunner") as MockRunner:
                            runner_instance = MagicMock()
                            runner_instance.run = mock_run
                            runner_instance.get_git_diff.return_value = ""
                            MockRunner.return_value = runner_instance

                            orchestrator = Orchestrator(run_id=42, job_config=job)
                            result = await orchestrator.run(
                                "Build a greeting endpoint", {}
                            )
                            assert result is not None

                            # Verify side effects in the DB
                            db = await aiosqlite.connect(db_path)
                            row = await (
                                await db.execute(
                                    "SELECT COUNT(*) FROM run_steps WHERE run_id = ?",
                                    (42,),
                                )
                            ).fetchone()
                            assert row[0] > 0
                            await db.close()

    asyncio.run(_run())
