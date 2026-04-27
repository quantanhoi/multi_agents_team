trung.quang@stud.h-da.de  
April 27, 2026


# I want to setup a system that consist of 3 LLMs, all host on ollama cloud, let's say 1 GLM5.1, 1 deepseek v4 pro, and 1 running kimi k2.6, 
they will have different roles, for example 1 will do planning, 1 will do the coding, and 1 will do the testing (both manual and automation test) 
all 3 of them will work on the same project, how can I do that?

[Inference] Short answer: yes, you can build this, but I cannot verify from the provided sources that Ollama Cloud has a built-in feature where 3 cloud models automatically share one project and work together by themselves.

Ollama says cloud models are in preview, and they let you run larger models on datacenter hardware while still using your local tools. [[1]](https://ollama.com/blog/cloud-models)  
GLM-5.1, DeepSeek-V4-Pro, and Kimi K2.6 are listed on Ollama’s cloud models page. [[2]](https://ollama.com/search?c=cloud)

[Inference] The best way to do this is to treat the 3 models as workers, and put one small app in the middle to coordinate them.

## A simple setup

[Inference] Use this pattern:

1. **One orchestrator app**
   - This is your controller.
   - It sends the right task to the right model.
   - It stores shared state.

2. **One shared Git repo**
   - All code lives in one repo.
   - The coder writes changes there.
   - The tester reads the changed files and test results from there.

3. **One shared task/state store**
   - Simple files are enough at first:
     - `plan.json`
     - `tasks.json`
     - `test_report.json`
     - `context.md`

4. **Three fixed roles**
   - **Planner model**
   - **Coder model**
   - **Tester model**

## Good role split

[Inference] This role split is reasonable based on the model descriptions, but it is still a design choice from me, not a documented Ollama rule.

- [Inference] **Kimi K2.6 for planning/coordinator** may be a good fit because Ollama describes it as strong in long-horizon coding, proactive autonomous execution, and swarm-based task orchestration. [[2]](https://ollama.com/search?c=cloud)
- [Inference] **GLM-5.1 for coding** may be a good fit because Ollama describes it as a flagship model for agentic engineering with stronger coding capability than its predecessor. [[2]](https://ollama.com/search?c=cloud)
- [Inference] **DeepSeek-V4-Pro for testing/review** may be a good fit because Ollama describes it as a frontier model with a 1M-token context window and three reasoning modes. [[2]](https://ollama.com/search?c=cloud)

## How they should work together

[Inference] A clean workflow looks like this:

### Step 1: Planner
The planner gets:
- your feature request
- current repo summary
- current open bugs
- current test status

[Inference] The planner should return only structured output like:
- goal
- tasks
- file targets
- risks
- acceptance criteria
- test ideas

### Step 2: Coder
The coder gets:
- the planner output
- relevant files
- repo rules
- coding style rules

[Inference] The coder should return:
- code patch or file changes
- short explanation
- notes for the tester

### Step 3: Tester
The tester gets:
- planner output
- coder changes
- automated test results
- lint/type-check output

[Inference] The tester should return:
- pass/fail
- bug list
- missing edge cases
- suggested fixes
- manual test checklist

### Step 4: Loop
[Inference] If tests fail, send the tester’s report back to the coder.  
[Inference] If tests pass, send the final result back to the planner for final review and next-step planning.

## Important idea: do not let them “chat freely”

[Inference] It is usually better to have the orchestrator control the flow, instead of letting all 3 models talk to each other with no rules.  
[Inference] If you let them talk freely, context can get messy, repeated, and expensive.

## What the shared project data should look like

[Inference] Keep a simple project folder like this:

```text
project/
  repo/                  # your app code
  state/
    context.md           # project summary
    plan.json            # planner output
    tasks.json           # task list + status
    test_report.json     # tester output
    handoff.md           # short notes between roles
  artifacts/
    lint.txt
    unit_tests.txt
    e2e_tests.txt
```

## Minimum orchestration logic

[Inference] A very small controller can do this:

```python
import json
import subprocess
from pathlib import Path

PLANNER_MODEL = "YOUR_PLANNER_MODEL"
CODER_MODEL = "YOUR_CODER_MODEL"
TESTER_MODEL = "YOUR_TESTER_MODEL"

STATE_DIR = Path("state")
ARTIFACTS_DIR = Path("artifacts")

STATE_DIR.mkdir(exist_ok=True)
ARTIFACTS_DIR.mkdir(exist_ok=True)


def call_model(model, system_prompt, user_prompt):
    """
    Replace this with your Ollama client call.
    Keep the same shape:
    return {"content": "...model output..."}
    """
    raise NotImplementedError


def read_repo_summary():
    context_file = STATE_DIR / "context.md"
    if context_file.exists():
        return context_file.read_text()
    return "No repo summary yet."


def save_json(path, data):
    path.write_text(json.dumps(data, indent=2))


def run_command(command):
    result = subprocess.run(command, capture_output=True, text=True, shell=True)
    return {
        "command": command,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def planner_step(feature_request):
    system_prompt = """
You are the planner.
Return JSON only with:
goal, tasks, files_needed, risks, acceptance_criteria, test_plan
"""
    user_prompt = f"""
Feature request:
{feature_request}

Repo summary:
{read_repo_summary()}
"""
    result = call_model(PLANNER_MODEL, system_prompt, user_prompt)
    plan = json.loads(result["content"])
    save_json(STATE_DIR / "plan.json", plan)
    return plan


def coder_step(plan, changed_files_text):
    system_prompt = """
You are the coder.
Follow the plan.
Return JSON only with:
summary, files_to_change, patch_or_full_files, notes_for_tester
"""
    user_prompt = f"""
Plan:
{json.dumps(plan, indent=2)}

Relevant files:
{changed_files_text}
"""
    result = call_model(CODER_MODEL, system_prompt, user_prompt)
    code_output = json.loads(result["content"])
    save_json(STATE_DIR / "coder_output.json", code_output)
    return code_output


def test_step(plan, coder_output):
    lint_result = run_command("ruff check .")
    unit_result = run_command("pytest -q")

    (ARTIFACTS_DIR / "lint.txt").write_text(
        f"EXIT={lint_result['exit_code']}\n{lint_result['stdout']}\n{lint_result['stderr']}"
    )
    (ARTIFACTS_DIR / "unit_tests.txt").write_text(
        f"EXIT={unit_result['exit_code']}\n{unit_result['stdout']}\n{unit_result['stderr']}"
    )

    system_prompt = """
You are the tester.
Return JSON only with:
status, bugs, manual_test_checklist, automation_gaps, next_action
"""
    user_prompt = f"""
Plan:
{json.dumps(plan, indent=2)}

Coder output:
{json.dumps(coder_output, indent=2)}

Lint result:
{json.dumps(lint_result, indent=2)}

Unit test result:
{json.dumps(unit_result, indent=2)}
"""
    result = call_model(TESTER_MODEL, system_prompt, user_prompt)
    test_report = json.loads(result["content"])
    save_json(STATE_DIR / "test_report.json", test_report)
    return test_report


def main(feature_request, relevant_files_text):
    plan = planner_step(feature_request)
    coder_output = coder_step(plan, relevant_files_text)
    test_report = test_step(plan, coder_output)

    print(json.dumps({
        "plan": plan,
        "coder_output": coder_output,
        "test_report": test_report
    }, indent=2))


if __name__ == "__main__":
    feature_request = "Add user login with email + password."
    relevant_files_text = "Paste important repo files here, or load them from disk."
    main(feature_request, relevant_files_text)
```

## What each model prompt should say

[Inference] Give each model a strict system prompt.

### Planner prompt
```text
You are the planner.
Your job is to break work into small steps.
Do not write code.
Return JSON only:
{
  "goal": "",
  "tasks": [],
  "files_needed": [],
  "risks": [],
  "acceptance_criteria": [],
  "test_plan": []
}
```

### Coder prompt
```text
You are the coder.
Write or edit code only from the approved plan.
Do not change unrelated files.
Return JSON only:
{
  "summary": "",
  "files_to_change": [],
  "patch_or_full_files": [],
  "notes_for_tester": []
}
```

### Tester prompt
```text
You are the tester.
Review the code and the test outputs.
Find bugs, edge cases, and missing tests.
Return JSON only:
{
  "status": "pass|fail",
  "bugs": [],
  "manual_test_checklist": [],
  "automation_gaps": [],
  "next_action": ""
}
```

## How manual testing fits in

[Inference] An LLM cannot do real human manual testing by itself unless you give it tools.  
[Inference] For web apps, the tester role becomes much stronger if you connect it to browser automation like Playwright.  
[Inference] In that setup, the tester model can:
- create test cases
- run browser scripts
- inspect screenshots/logs
- report bugs

[Inference] Without tools, “manual testing” from the tester model is mostly:
- review checklists
- edge case thinking
- expected user-flow analysis

## Practical rules that help a lot

[Inference] Use these rules from the start:

- planner only plans
- coder only changes code
- tester only reviews and tests
- all outputs are JSON
- all file writes go through the orchestrator
- all test commands are run by the orchestrator, not by raw model text
- keep short summaries in `context.md`
- keep full logs in `artifacts/`

## Best first version

[Inference] If you want the easiest version first, build this:

- **Kimi K2.6** = planner
- **GLM-5.1** = coder
- **DeepSeek-V4-Pro** = tester
- one Python orchestrator
- one Git repo
- pytest + linter
- JSON handoffs only

## One thing I cannot verify

I cannot verify from the provided sources that Ollama Cloud currently gives you a built-in “multi-agent project workspace” for these 3 models out of the box.  
What I can verify is that Ollama Cloud is in preview and that these models appear on the cloud models page. [[2]](https://ollama.com/search?c=cloud)

[Inference] If you want, I can give you one of these next:

1. a **real Python version** wired for Ollama API  
2. a **Node.js version**  
3. a **LangGraph-style version**  
4. a version for **web app testing with Playwright**


### References

1. **GitHub - ollama/ollama: Get up and running with Kimi-K2.5, GLM-5, MiniMax, DeepSeek, gpt-oss, Qwen, Gemma and other models. · GitHub**. [https://github.com](https://github.com/ollama/ollama)
2. **Releases · ollama/ollama**. [https://github.com](https://github.com/ollama/ollama/releases)
3. **Cloud models · Ollama**. [https://ollama.com](https://ollama.com/search?c=cloud)
4. **DeepSeek V4 Ollama Install: Step by Step (Free) | AI Profit Boardroom Blog**. [https://aiprofitboardroom.com](https://aiprofitboardroom.com/blog/deepseek-v4-ollama/)
5. **🚀 Setting Up Ollama & Running DeepSeek R1 Locally for a Powerful RAG System - DEV Community**. [https://dev.to](https://dev.to/ajmal_hasan/setting-up-ollama-running-deepseek-r1-locally-for-a-powerful-rag-system-4pd4)
6. **Ollama Cloud Support Deepseek 3.2 · Issue #13294 · ollama/ollama**. [https://github.com](https://github.com/ollama/ollama/issues/13294)
7. **Cloud models · Ollama Blog**. [https://ollama.com](https://ollama.com/blog/cloud-models)
8. **r/ollama on Reddit: Sweet spot…Cloud & local LLM setup + Mission Control**. [https://www.reddit.com](https://www.reddit.com/r/ollama/comments/1sou2m9/sweet_spotcloud_local_llm_setup_mission_control/)
9. **r/ollama on Reddit: Why Ollama Cloud doesn't have DeepSeek V4 Pro and Qwen3.6?**. [https://www.reddit.com](https://www.reddit.com/r/ollama/comments/1sw512f/why_ollama_cloud_doesnt_have_deepseek_v4_pro_and/)
10. **r/ollama**. [https://www.reddit.com](https://www.reddit.com/r/ollama/)
