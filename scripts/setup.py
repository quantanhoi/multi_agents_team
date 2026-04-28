#!/usr/bin/env python3
"""
Multi-Agent Studio — Interactive Setup Script

Features:
  - Lists available models from your Ollama endpoint
  - Lets you pick a model and assign a role (planner/coder/tester)
  - Auto-creates an agent preset via the backend API
  - Starts Docker containers with smart port management
  - Verifies everything is healthy before exiting

Usage:
  python scripts/setup.py
  OLLAMA_ENDPOINT=http://my-ollama:11435 python scripts/setup.py
"""

import os
import sys
import json
import time
import subprocess
import urllib.request
import urllib.error
import socket

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_PORT = int(os.environ.get("BACKEND_PORT", "8002"))
FRONTEND_PORT = int(os.environ.get("FRONTEND_PORT", "5173"))
OLLAMA_ENDPOINT = os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11435").rstrip("/")
BACKEND_URL = f"http://localhost:{BACKEND_PORT}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def print_step(n: int, text: str):
    print(f"\n{'='*60}\n  Step {n}: {text}\n{'='*60}")

def print_ok(text: str):
    print(f"  [OK] {text}")

def print_warn(text: str):
    print(f"  [WARN] {text}")

def print_err(text: str):
    print(f"  [ERR] {text}")

def ask(question: str, default: str = "") -> str:
    prompt = f"{question}"
    if default:
        prompt += f" [{default}]"
    prompt += ": "
    answer = input(prompt).strip()
    return answer if answer else default

def ask_yn(question: str, default: bool = True) -> bool:
    suffix = " [Y/n]" if default else " [y/N]"
    answer = input(f"{question}{suffix}: ").strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes")

def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) != 0

def find_free_port(start: int, max_attempts: int = 20) -> int:
    for p in range(start, start + max_attempts):
        if port_free(p):
            return p
    raise RuntimeError(f"No free port found starting from {start}")

def http_get_json(url: str, timeout: int = 10) -> dict:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def http_post_json(url: str, data: dict, timeout: int = 10) -> dict:
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST",
                                   headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

# ---------------------------------------------------------------------------
# Step 1: Docker check
# ---------------------------------------------------------------------------

def step1_docker():
    print_step(1, "Checking Docker & Docker Compose")
    try:
        subprocess.run(["docker", "compose", "version"], check=True, capture_output=True)
        print_ok("Docker Compose is available")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_err("Docker Compose is not installed or not in PATH.")
        print("  Install: https://docs.docker.com/compose/install/")
        sys.exit(1)

# ---------------------------------------------------------------------------
# Step 2: Port management
# ---------------------------------------------------------------------------

def step2_ports() -> tuple[int, int]:
    print_step(2, "Port Check")
    global BACKEND_PORT, FRONTEND_PORT

    backend_ok = port_free(BACKEND_PORT)
    frontend_ok = port_free(FRONTEND_PORT)

    if backend_ok and frontend_ok:
        print_ok(f"Backend port {BACKEND_PORT} is free")
        print_ok(f"Frontend port {FRONTEND_PORT} is free")
        return BACKEND_PORT, FRONTEND_PORT

    if not backend_ok:
        print_warn(f"Backend port {BACKEND_PORT} is already in use")
    if not frontend_ok:
        print_warn(f"Frontend port {FRONTEND_PORT} is already in use")

    if ask_yn("Find and use the next available ports?"):
        if not backend_ok:
            BACKEND_PORT = find_free_port(BACKEND_PORT + 1)
            print_ok(f"Backend will use port {BACKEND_PORT}")
        if not frontend_ok:
            FRONTEND_PORT = find_free_port(FRONTEND_PORT + 1)
            print_ok(f"Frontend will use port {FRONTEND_PORT}")
    else:
        print_err("Cannot proceed with occupied ports.")
        print("  Set custom ports: BACKEND_PORT=xxxx FRONTEND_PORT=yyyy python scripts/setup.py")
        sys.exit(1)

    return BACKEND_PORT, FRONTEND_PORT

# ---------------------------------------------------------------------------
# Step 3: Ollama model discovery
# ---------------------------------------------------------------------------

def step3_ollama_models() -> list[dict]:
    print_step(3, "Discovering Ollama Models")
    print(f"  Endpoint: {OLLAMA_ENDPOINT}")

    try:
        data = http_get_json(f"{OLLAMA_ENDPOINT}/api/tags", timeout=10)
        models = data.get("models", [])
        if not models:
            print_warn("No models found on this Ollama instance.")
            print("  Make sure Ollama is running and has models pulled.")
            sys.exit(1)

        print_ok(f"Found {len(models)} model(s)")
        return models
    except urllib.error.URLError as e:
        print_err(f"Cannot reach Ollama at {OLLAMA_ENDPOINT}")
        print(f"  Reason: {e.reason}")
        print("  - Is Ollama running?")
        print("  - Is the endpoint correct? Set via OLLAMA_ENDPOINT=...")
        sys.exit(1)
    except Exception as e:
        print_err(f"Unexpected error fetching models: {e}")
        sys.exit(1)

# ---------------------------------------------------------------------------
# Step 4: Interactive agent creation
# ---------------------------------------------------------------------------

def step4_create_agent(models: list[dict]) -> dict:
    print_step(4, "Create Agent Preset")

    # Show model list
    print("\n  Available models:")
    for i, m in enumerate(models, 1):
        name = m.get("name", m.get("model", "unknown"))
        size = m.get("size", 0)
        size_str = f"{size / 1e9:.1f} GB" if size else "size unknown"
        print(f"    {i}. {name} ({size_str})")

    while True:
        choice = ask("Pick a model by number")
        if choice.isdigit() and 1 <= int(choice) <= len(models):
            selected = models[int(choice) - 1]
            break
        print_warn("Invalid choice. Try again.")

    model_name = selected.get("name", selected.get("model", "unknown"))
    print_ok(f"Selected model: {model_name}")

    # Role selection
    print("\n  Roles:")
    print("    1. planner  — breaks work into phases, writes roadmaps")
    print("    2. coder    — writes/edits code from approved plans")
    print("    3. tester   — reviews code, finds bugs, runs tests")

    while True:
        role_choice = ask("Pick a role by number", "2")
        roles = {"1": "planner", "2": "coder", "3": "tester"}
        role = roles.get(role_choice)
        if role:
            break
        print_warn("Invalid choice. Try again.")

    # Auto-generated defaults based on role
    defaults = {
        "planner": (
            f"{model_name.split(':')[0].title()} Planner",
            "You are the planner. Your job is to break work into small phases and produce a roadmap. Do not write code. Return JSON only with: goal, roadmap (array of phases with name, tasks, definition_of_done for both coder and tester), files_needed, risks, human_input_request (null or object)."
        ),
        "coder": (
            f"{model_name.split(':')[0].title()} Coder",
            "You are the coder. Write or edit code only from the approved plan. Do not change unrelated files. Return JSON only with: summary, files_changed, patch_or_full_files (array of {path, content}), notes_for_tester, human_input_request (null or object)."
        ),
        "tester": (
            f"{model_name.split(':')[0].title()} Tester",
            "You are the tester. Review the code and test outputs. Find bugs, edge cases, and missing tests. Return JSON only with: status (pass|fail), bugs (array of {severity, description, file}), definition_of_done_check (for_coder, for_tester), manual_test_checklist, automation_gaps, next_action (fix_bugs|continue|done), human_input_request (null or object)."
        ),
    }

    default_name, default_prompt = defaults[role]

    name = ask("Agent name", default_name)
    temp = float(ask("Temperature", "0.3"))

    print("\n  System prompt (press Enter to accept default):")
    print(f"    {default_prompt[:100]}...")
    custom_prompt = ask("Or type a custom prompt", default_prompt)

    agent_payload = {
        "name": name,
        "role": role,
        "model_name": model_name,
        "system_prompt": custom_prompt,
        "temperature": temp,
        "ollama_endpoint": OLLAMA_ENDPOINT,
    }

    print(f"\n  Creating agent via {BACKEND_URL}/api/agents ...")
    try:
        result = http_post_json(f"{BACKEND_URL}/api/agents", agent_payload, timeout=10)
        print_ok(f"Agent created! ID={result['id']}, Name={result['name']}")
        return result
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print_err(f"Backend returned {e.code}: {body}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print_err(f"Cannot reach backend at {BACKEND_URL}")
        print("  Is the backend running? The script will try to start it next.")
        return agent_payload  # return payload so user can retry after docker starts

# ---------------------------------------------------------------------------
# Step 5: Docker Compose up
# ---------------------------------------------------------------------------

def step5_docker_up(backend_port: int, frontend_port: int):
    print_step(5, "Starting Docker Containers")

    # Check if already running
    try:
        out = subprocess.run(
            ["docker", "compose", "ps", "--format", "json"],
            cwd=BASE_DIR, capture_output=True, text=True, check=True
        )
        running = json.loads(out.stdout) if out.stdout.strip() else []
        if running:
            print_ok("Docker containers are already running")
            return
    except Exception:
        pass

    env = os.environ.copy()
    env["BACKEND_PORT"] = str(backend_port)
    env["FRONTEND_PORT"] = str(frontend_port)

    print(f"  docker compose up -d (backend:{backend_port}, frontend:{frontend_port})")
    subprocess.run(
        ["docker", "compose", "up", "-d"],
        cwd=BASE_DIR, env=env, check=True
    )
    print_ok("Containers started")

    # Wait for backend health
    print("  Waiting for backend health check...")
    for i in range(30):
        try:
            health = http_get_json(f"{BACKEND_URL}/api/health", timeout=2)
            if health.get("status") == "ok":
                print_ok("Backend is healthy")
                return
        except Exception:
            pass
        time.sleep(1)
    print_err("Backend did not become healthy within 30 seconds.")
    print("  Check logs: docker logs multi-agent-backend")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Step 6: Verify & summary
# ---------------------------------------------------------------------------

def step6_verify(agent: dict, backend_port: int, frontend_port: int):
    print_step(6, "Verification & Summary")

    try:
        agents = http_get_json(f"{BACKEND_URL}/api/agents", timeout=5)
        print_ok(f"Backend API reachable — {len(agents)} agent(s) in library")
    except Exception as e:
        print_warn(f"Backend API check failed: {e}")

    try:
        jobs = http_get_json(f"{BACKEND_URL}/api/jobs", timeout=5)
        print_ok(f"Jobs API reachable — {len(jobs)} job(s) configured")
    except Exception:
        pass

    print("\n" + "="*60)
    print("  Setup complete!")
    print("="*60)
    print(f"  Frontend:  http://localhost:{frontend_port}")
    print(f"  Backend:   http://localhost:{backend_port}")
    print(f"  Ollama:    {OLLAMA_ENDPOINT}")
    if agent and "id" in agent:
        print(f"  New Agent: {agent['name']} (ID={agent['id']}, role={agent['role']})")
    print("\n  Next steps:")
    print("    1. Open the frontend URL in your browser")
    print("    2. Go to Settings and set your Working Directory")
    print("    3. Go to Run Console, pick a job, and start a run")
    print("\n  Useful commands:")
    print(f"    docker logs -f multi-agent-backend")
    print(f"    docker logs -f multi-agent-frontend")
    print("="*60)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(r"""
  __  __       _ _   _             _         _
 |  \/  |     | | | (_)           | |       | |
 | \  / |_   _| | |_ _ _ __   __ _| | ____ _| |_ ___ _ __
 | |\/| | | | | | __| | '_ \ / _` | |/ / _` | __/ _ \ '__|
 | |  | | |_| | | |_| | | | | (_| |   < (_| | ||  __/ |
 |_|  |_|\__,_|_|\__|_|_| |_|\__,_|_|\_\__,_|\__\___|_|

           Interactive Setup Script
""")

    # Override BACKEND_URL in case ports changed
    global BACKEND_URL
    BACKEND_URL = f"http://localhost:{BACKEND_PORT}"

    step1_docker()
    backend_port, frontend_port = step2_ports()
    models = step3_ollama_models()

    # Start docker first so the backend API is available for agent creation
    step5_docker_up(backend_port, frontend_port)

    agent = step4_create_agent(models)
    step6_verify(agent, backend_port, frontend_port)

if __name__ == "__main__":
    main()
