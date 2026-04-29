#!/usr/bin/env python3
"""Multi-Agent Studio — CLI Runner.

Replaces the React frontend with a simple command-line interface.
Handles: job selection, feature request, real-time run monitoring,
agent output display, human-in-the-loop prompts, step history.

Usage:
    python cli.py                    # Interactive mode
    python cli.py --job 2 "Build a portfolio site"  # One-shot mode
"""

import sys
import json
import time
import textwrap
import urllib.request
import urllib.error
import argparse
from datetime import datetime

BASE = "http://localhost:8002"

def req(method, path, body=None, timeout=5):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"} if body else {}
    rq = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(rq, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode(), "status": e.code}
    except Exception as e:
        return {"error": str(e)}


def print_banner():
    print()
    print(" ╔══════════════════════════════════════════════════════════╗")
    print(" ║         Multi-Agent Studio — CLI Runner                ║")
    print(" ║  Planner | Coder | Tester — Sequential Pipeline         ║")
    print(" ╚══════════════════════════════════════════════════════════╝")
    print()


def print_jobs():
    jobs = req("GET", "/api/jobs")
    if isinstance(jobs, dict) and "error" in jobs:
        print(f"[ERROR] Could not fetch jobs: {jobs['error']}")
        return None

    print("Available Jobs:")
    for j in jobs:
        print(f"  {j['id']}: {j['name']} — max_iter={j['max_iterations']} — DoD={j.get('definition_of_done','')[:50]}")
    return jobs


def print_agents():
    agents = req("GET", "/api/agents")
    if isinstance(agents, dict) and "error" in agents:
        print(f"[ERROR] Could not fetch agents: {agents['error']}")
        return None

    print("Agents:")
    for a in agents:
        print(f"  {a['id']}: {a['name']} ({a['role']}) → {a['model_name']}")
    return agents


def select_job(jobs):
    try:
        choice = input("\nSelect job ID (or Enter for #2): ").strip()
        job_id = int(choice) if choice else 2
        for j in jobs:
            if j["id"] == job_id:
                return j
        print(f"Job {job_id} not found. Using #2.")
        return next(j for j in jobs if j["id"] == 2)
    except (ValueError, StopIteration):
        print("Invalid selection. Using first job.")
        return jobs[0]


def run_job(job):
    feature = input(f"\nFeature request [{job['name']}]: ").strip()
    if not feature:
        feature = "Build the requested feature"

    notes = input("Extra notes (optional, Enter to skip): ").strip()

    print(f"\n[STARTING] Run for job '{job['name']}'...")
    run = req("POST", "/api/runs", {
        "job_id": job["id"],
        "feature_request": feature,
        "context": {
            "selected_files": [],
            "known_bugs": [],
            "constraints": [],
            "extra_notes": notes,
        }
    }, timeout=10)

    if isinstance(run, dict) and run.get("error"):
        print(f"[ERROR] Could not start run: {run['error']}")
        return None

    print(f"[RUN #{run['id']}] Status: {run['status']}")
    return run


def monitor_run(run_id):
    print(f"\n[MONITORING] Run #{run_id}. Press Ctrl+C to stop.")
    print("─" * 60)

    last_status = None
    last_step_count = 0
    human_pending = False

    try:
        while True:
            run = req("GET", f"/api/runs/{run_id}", timeout=5)
            if isinstance(run, dict) and run.get("error"):
                time.sleep(2)
                continue

            status = run.get("status", "unknown")
            steps = req("GET", f"/api/runs/{run_id}/steps", timeout=5)
            if isinstance(steps, dict) and steps.get("error"):
                steps = []

            # Status change
            if status != last_status:
                print(f"\n  [STATUS] {status.upper()}")
                last_status = status

            # New steps
            if len(steps) > last_step_count:
                for s in steps[last_step_count:]:
                    print_step(s)
                last_step_count = len(steps)

            # Human-in-the-loop
            if status == "waiting_for_human" and not human_pending:
                handle_human_input(run_id)
                human_pending = True

            if status not in ("waiting_for_human",):
                human_pending = False

            # Done / failed / stopped
            if status in ("done", "failed", "stopped"):
                print(f"\n[FINISHED] Run #{run_id} — {status.upper()}")
                print("─" * 60)
                print_summary(run_id)
                return

            time.sleep(2)
    except KeyboardInterrupt:
        print(f"\n[STOPPING] Run #{run_id}...")
        req("POST", f"/api/runs/{run_id}/stop", timeout=5)
        print("Stopped.")


def print_step(step):
    role = step.get("agent", "?")
    stype = step.get("step_type", "?")
    num = step.get("step_number", "?")
    latency = step.get("latency_ms", 0)
    files = step.get("files_changed", "[]")
    error = step.get("error")

    # Color coding by role
    color = {"planner": "\033[36m", "coder": "\033[32m", "tester": "\033[31m"}.get(role, "\033[0m")
    reset = "\033[0m"

    tag = f"{color}[{role.upper()}]{reset}"
    print(f"\n  Step {num:2d} {tag} {stype:8s} ({latency/1000:5.1f}s)")

    if error:
        print(f"    ⚠️  ERROR: {error}")
        return

    output = step.get("output")
    try:
        if isinstance(output, str):
            parsed = json.loads(output)
        else:
            parsed = output

        summary = parsed.get("summary") or parsed.get("raw_output", "")[:200]
        if summary:
            wrapped = textwrap.fill(summary, width=54, initial_indent="    ", subsequent_indent="    ")
            print(wrapped)

        if isinstance(files, str):
            try:
                files = json.loads(files)
            except:
                files = []

        if files and files != []:
            if len(files) <= 5:
                print(f"    📄 Files: {', '.join(files)}")
            else:
                print(f"    📄 Files: {len(files)} files written")

        if parsed.get("human_input_request"):
            msg = parsed["human_input_request"].get("message", "Agent needs input")
            wrapped = textwrap.fill(msg, width=54, initial_indent="    🤖 ", subsequent_indent="       ")
            print(wrapped)

    except (json.JSONDecodeError, TypeError):
        if output:
            print(f"    {str(output)[:200]}")


def handle_human_input(run_id):
    run = req("GET", f"/api/runs/{run_id}", timeout=5)
    if isinstance(run, dict) and run.get("error"):
        return

    requests = run.get("human_requests", [])
    if not requests:
        return

    last = requests[-1]
    req_msg = last.get("request", {}).get("message", "Agent needs input")

    print(f"\n{'─' * 60}")
    print(f"  🤖 HUMAN INPUT REQUIRED:")
    wrapped = textwrap.fill(req_msg, width=54, initial_indent="  ", subsequent_indent="  ")
    print(wrapped)
    print(f"{'─' * 60}")

    response = input("  Your response: ").strip()
    if not response:
        response = "Continue with the current approach."

    print(f"  [Sending response...]")
    result = req("POST", f"/api/runs/{run_id}/resume", {
        "response_text": response,
        "uploaded_files": []
    }, timeout=10)
    if isinstance(result, dict) and result.get("error"):
        print(f"  [ERROR] {result['error']}")
    else:
        print(f"  [Resumed]")


def print_summary(run_id):
    steps = req("GET", f"/api/runs/{run_id}/steps", timeout=5)
    if isinstance(steps, dict) and steps.get("error"):
        print("Could not fetch step summary.")
        return

    total = len(steps)
    total_time = sum(s.get("latency_ms", 0) for s in steps)
    files_written = 0
    errors = 0

    for s in steps:
        f = s.get("files_changed", "[]")
        try:
            fl = json.loads(f) if isinstance(f, str) else f
            if fl and fl != []:
                files_written += 1
        except:
            pass
        if s.get("error"):
            errors += 1

    print(f"\n  Total steps:     {total}")
    print(f"  Total time:      {total_time/1000:.1f}s")
    print(f"  Files written:   {files_written}")
    print(f"  Errors:          {errors}")

    # Show generated files tree
    print(f"\n  Generated files:")
    for s in steps:
        f = s.get("files_changed", "[]")
        try:
            fl = json.loads(f) if isinstance(f, str) else f
            if fl and fl != []:
                for path in fl:
                    print(f"    ├─ {path}")
        except:
            pass


def main():
    parser = argparse.ArgumentParser(description="Multi-Agent Studio CLI")
    parser.add_argument("--job", type=int, help="Job ID to run")
    parser.add_argument("feature_request", nargs="?", help="Feature request text")
    args = parser.parse_args()

    print_banner()

    # Health check
    settings = req("GET", "/api/settings", timeout=3)
    if isinstance(settings, dict) and settings.get("error"):
        print(f"[ERROR] Backend not responding at {BASE}")
        print(f"  {settings.get('error')}")
        sys.exit(1)
    print(f"[OK] Backend connected. Working dir: {settings.get('working_dir', 'N/A')}")

    jobs = print_jobs()
    if not jobs:
        sys.exit(1)

    print_agents()

    if args.job and args.feature_request:
        # One-shot mode
        job = next((j for j in jobs if j["id"] == args.job), None)
        if not job:
            print(f"[ERROR] Job {args.job} not found")
            sys.exit(1)

        run = req("POST", "/api/runs", {
            "job_id": job["id"],
            "feature_request": args.feature_request,
            "context": {"selected_files": [], "known_bugs": [], "constraints": [], "extra_notes": ""},
        }, timeout=10)
    else:
        # Interactive mode
        job = select_job(jobs)
        run = run_job(job)

    if not run or run.get("error"):
        print(f"[ERROR] Failed to start run: {run.get('error', 'unknown')}")
        sys.exit(1)

    monitor_run(run["id"])


if __name__ == "__main__":
    main()
