"""Seed the database with 3 default agents and 1 default job."""
import asyncio
import aiosqlite
from database import DB_PATH, init_db


async def seed():
    await init_db()
    db = await aiosqlite.connect(DB_PATH)

    # Create 3 default agents
    agents = [
        ("Kimi Planner", "planner", "kimi-k2.6",
         "You are the planner. Your job is to break work into small phases and produce a roadmap. Do not write code. Return JSON only with: goal, roadmap (array of phases with name, tasks, definition_of_done for both coder and tester), files_needed, risks, human_input_request (null or object)."),
        ("GLM Coder", "coder", "glm-5.1",
         "You are the coder. Write or edit code only from the approved plan. Do not change unrelated files. Return JSON only with: summary, files_changed, patch_or_full_files (array of {path, content}), notes_for_tester, human_input_request (null or object)."),
        ("DeepSeek Tester", "tester", "deepseek-v4-pro",
         "You are the tester. Review the code and test outputs. Find bugs, edge cases, and missing tests. Return JSON only with: status (pass|fail), bugs (array of {severity, description, file}), definition_of_done_check (for_coder, for_tester), manual_test_checklist, automation_gaps, next_action (fix_bugs|continue|done), human_input_request (null or object)."),
    ]

    agent_ids = []
    for name, role, model, prompt in agents:
        cursor = await db.execute(
            "INSERT INTO agents (name, role, model_name, system_prompt, temperature) VALUES (?, ?, ?, ?, 0.3)",
            (name, role, model, prompt)
        )
        agent_ids.append(cursor.lastrowid)

    # Create 1 default job
    import json
    await db.execute(
        "INSERT INTO jobs (name, description, planner_agent_id, coder_agent_id, tester_agent_id, agent_overrides, loop_mode, max_iterations) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("Default Full-Stack Feature",
         "Standard 3-agent pipeline: planner-led roadmap with coder/tester reviews, automatic loop.",
         agent_ids[0], agent_ids[1], agent_ids[2],
         json.dumps({}),
         "automatic", 5)
    )

    await db.commit()
    await db.close()
    print(f"Seeded {len(agent_ids)} agents and 1 job.")


if __name__ == "__main__":
    asyncio.run(seed())
