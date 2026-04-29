#!/usr/bin/env python3
"""
opencode fallback CLI for testing multi-agent orchestrator.

Replaces the unavailable opencode CLI by calling Ollama API directly
and handling basic file-write hints from model responses.

Usage:
    opencode run --model <model> <prompt>
"""

import sys
import os
import json
import re
import subprocess
import argparse
# Add backend to path for ollama_client
sys.path.insert(0, '/app')

OLLAMA_URL = os.environ.get('OLLAMA_ENDPOINT', 'http://host.docker.internal:11435')

def call_ollama(prompt: str, model: str, system: str = ""):
    """Call Ollama /api/chat endpoint directly."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    
    payload = json.dumps({"model": model, "messages": messages, "stream": False})
    
    try:
        import urllib.request
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/chat",
            data=payload.encode(),
            headers={"Content-Type": "application/json"},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
            return data.get("message", {}).get("content", data.get("content", ""))
    except Exception as e:
        print(f"[opencode-fallback] Error calling Ollama: {e}", file=sys.stderr)
        return json.dumps({
            "error": str(e),
            "human_input_request": {
                "requested_by": "system",
                "message": f"Ollama endpoint at {OLLAMA_URL} unreachable: {e}",
                "input_type": "text"
            }
        })

def write_files_from_response(text: str):
    """Attempt to extract and write files from code blocks."""
    cwd = os.getcwd()
    pattern = re.compile(r'```(\w+)?\n(.*?)\n```', re.DOTALL)
    matches = pattern.findall(text)
    
    written = []
    for lang, code in matches:
        lines = code.strip().split('\n')
        if not lines:
            continue
        # Detect filename from first-line comment hint
        first = lines[0]
        fname = None
        for prefix in ('# File:', '// File:', '# FILE:', '/* File:'):
            if prefix in first:
                fname = first.split(prefix)[-1].strip().strip('*/#').strip()
                break
        # Guess filename from language if no explicit hint
        if not fname:
            if lang in ('html', 'htm'):
                fname = 'index.html'
            elif lang in ('python', 'py'):
                fname = 'main.py'
            elif lang in ('jsx', 'tsx', 'react') or ('import React' in code):
                fname = 'App.jsx'
            elif lang in ('css', 'tailwind'):
                fname = 'index.css'
            elif lang in ('js', 'javascript'):
                fname = 'app.js'
            elif lang in ('sql'):
                fname = 'schema.sql'
            else:
                continue  # Unknown file type, skip
        
        # Remove the file-comment line from output
        if '# File:' in first or '// File:' in first or '# FILE:' in first or '/* File:' in first:
            code = '\n'.join(lines[1:])
        
        full = os.path.join(cwd, fname)
        os.makedirs(os.path.dirname(full) or '.', exist_ok=True)
        with open(full, 'w') as f:
            f.write(code)
        written.append(fname)
        print(f"[opencode-fallback] Wrote: {fname}", file=sys.stderr)
    
    return written

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', nargs='?', default='run')
    parser.add_argument('--model', default='glm-5.1')
    parser.add_argument('--dangerously-skip-permissions', action='store_true')
    parser.add_argument('prompt_parts', nargs='*')
    args = parser.parse_args()
    
    prompt = ' '.join(args.prompt_parts) if args.prompt_parts else sys.stdin.read()
    model = args.model
    
    # Role-based system prompt
    if 'kimi' in model.lower():
        system = ("You are the planner. Break work into phases and produce a roadmap. "
                  "Return JSON only with: goal, roadmap (array of phases), files_needed, risks, "
                  "human_input_request (null or object).")
    elif 'glm' in model.lower() or 'claude' in model.lower():
        system = ("You are the coder. Write or edit code based on the plan. "
                  "Return JSON only with: summary, files_changed, patch_or_full_files "
                  "(array of {path, content}), notes_for_tester.")
    elif 'deepseek' in model.lower():
        system = ("You are the tester. Review code and test outputs. "
                  "Return JSON only with: status (pass|fail), bugs, manual_test_checklist, "
                  "automation_gaps, next_action.")
    else:
        system = "You are an AI assistant. Provide helpful JSON responses."
    
    print(f"[opencode-fallback] model={model}, calling {OLLAMA_URL}", file=sys.stderr)
    content = call_ollama(prompt, model, system)
    
    # Try to parse JSON; if not valid, wrap raw text
    try:
        json.loads(content)
        print(content)
    except json.JSONDecodeError:
        # Write files from code blocks
        written = write_files_from_response(content)
        output = {
            "raw_output": content[:2000],
            "files_changed": written,
            "human_input_request": None,
            "summary": f"Generated {len(written)} file(s): {written}"
        }
        print(json.dumps(output, indent=2))

if __name__ == '__main__':
    main()
