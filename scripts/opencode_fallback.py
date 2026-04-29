#!/usr/bin/env python3
"""
Fallback 'opencode' CLI for testing.

This script mimics the opencode CLI interface used by the orchestrator.
It calls the Ollama API directly through the backend's ollama_client.py.
Since the real opencode CLI is not yet available via npm,
this fallback generates code suggestions and writes files.

Usage:
    opencode run --model MODEL [--dangerously-skip-permissions] <prompt>
"""

import sys
import os
import argparse
import json
import re
import subprocess

# Add backend directory to path to import ollama_client
sys.path.insert(0, '/app')


def call_ollama(prompt: str, model: str, system_prompt: str = ""):
    """Call Ollama API via the backend's client."""
    try:
        from ollama_client import OllamaClient

        client = OllamaClient()
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = client.chat(model=model, messages=messages)
        content = response.get("content", "")
        return content
    except Exception as e:
        print(f"Error calling Ollama: {e}", file=sys.stderr)
        return f"Error: {e}"


def extract_code_blocks(text: str):
    """Extract code blocks from markdown/text output."""
    # Find ```language\ncode\n``` patterns
    pattern = r'```(?:\w+)?\n(.*?)\n```'
    matches = re.findall(pattern, text, re.DOTALL)
    return matches


def main():
    parser = argparse.ArgumentParser(description='OpenCode fallback CLI')
    parser.add_argument('command', nargs='?', default='run', help='Command (run)')
    parser.add_argument('--model', default='glm-5.1', help='Model to use')
    parser.add_argument('--dangerously-skip-permissions', action='store_true',
                        help='Skip permission checks (ignored in fallback)')
    parser.add_argument('prompt', nargs='*', help='Prompt text')

    args = parser.parse_args()

    full_prompt = ' '.join(args.prompt) if args.prompt else sys.stdin.read()

    # Determine role from worktree/ directory context
    cwd = os.getcwd()
    system_prompt = ""
    if 'planner' in cwd.lower() or 'plan' in full_prompt[:100].lower():
        system_prompt = "You are a planning agent. Produce JSON output with plan/roadmap only."
    elif 'coder' in cwd.lower() or 'code' in full_prompt[:100].lower():
        system_prompt = "You are a coding agent. Write code and return JSON with files_changed array."
    elif 'tester' in cwd.lower() or 'test' in full_prompt[:100].lower():
        system_prompt = "You are a testing agent. Review code and return test results."

    print(f"Running opencode fallback with model={args.model}", file=sys.stderr)

    content = call_ollama(full_prompt, args.model, system_prompt)

    # If response contains code blocks, write them to files
    code_blocks = extract_code_blocks(content)
    if code_blocks:
        for idx, code in enumerate(code_blocks):
            # Try to infer filename from comment in first line
            lines = code.split('\n')
            first_line = lines[0] if lines else ''

            # Check for explicit file write instructions
            if '# File:' in first_line:
                filename = first_line.split('# File:')[-1].strip()
            elif '// File:' in first_line:
                filename = first_line.split('// File:')[-1].strip()
            else:
                # Try to detect file type
                if '<!DOCTYPE html>' in code or code.startswith('<'):
                    filename = 'index.html'
                elif 'import ' in code and ('fastapi' in code or 'from fastapi' in code):
                    filename = 'main.py'
                elif 'import ' in code and ('react' in code.lower() or 'jsx' in code.lower()):
                    filename = 'App.jsx'
                else:
                    filename = f'output_{idx}.txt'

            # Remove File: comment from first line
            if 'File:' in first_line:
                code = '\n'.join(lines[1:])

            full_path = os.path.join(cwd, filename)
            os.makedirs(os.path.dirname(full_path) or '.', exist_ok=True)
            with open(full_path, 'w') as f:
                f.write(code)
            print(f"Wrote: {filename}", file=sys.stderr)

    print(content)
    return 0


if __name__ == '__main__':
    sys.exit(main())
