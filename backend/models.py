from pydantic import BaseModel
from typing import Optional, List
from enum import Enum

class AgentRole(str, Enum):
    planner = "planner"
    coder = "coder"
    tester = "tester"

class AgentCreate(BaseModel):
    name: str
    role: AgentRole
    model_name: str
    system_prompt: str
    temperature: float = 0.3
    ollama_endpoint: str = "http://localhost:11435"
    api_key: str = ""

class AgentUpdate(BaseModel):
    name: Optional[str] = None
    model_name: Optional[str] = None
    system_prompt: Optional[str] = None
    temperature: Optional[float] = None
    ollama_endpoint: Optional[str] = None
    api_key: Optional[str] = None

class AgentResponse(BaseModel):
    id: int
    name: str
    role: str
    model_name: str
    system_prompt: str
    temperature: float
    ollama_endpoint: str
    api_key: str
    created_at: str
    updated_at: str

class AgentOverride(BaseModel):
    model_name: Optional[str] = None
    temperature: Optional[float] = None
    system_prompt_append: Optional[str] = None

class JobCreate(BaseModel):
    name: str
    description: str = ""
    planner_agent_id: int
    coder_agent_id: int
    tester_agent_id: int
    agent_overrides: dict = {}
    loop_mode: str = "automatic"
    max_iterations: int = 5
    definition_of_done: str = ""

class JobUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    planner_agent_id: Optional[int] = None
    coder_agent_id: Optional[int] = None
    tester_agent_id: Optional[int] = None
    agent_overrides: Optional[dict] = None
    loop_mode: Optional[str] = None
    max_iterations: Optional[int] = None

class JobResponse(BaseModel):
    id: int
    name: str
    description: str
    planner_agent_id: int
    coder_agent_id: int
    tester_agent_id: int
    agent_overrides: dict
    loop_mode: str
    max_iterations: int
    definition_of_done: str
    created_at: str
    updated_at: str

class RunContext(BaseModel):
    selected_files: List[str] = []
    known_bugs: List[str] = []
    constraints: List[str] = []
    extra_notes: str = ""

class RunStart(BaseModel):
    job_id: int
    feature_request: str
    context: RunContext = RunContext()

class HumanResponse(BaseModel):
    response_text: str = ""
    uploaded_files: List[str] = []

class RunResponse(BaseModel):
    id: int
    job_id: int
    status: str
    feature_request: str
    context: dict
    iterations: int
    roadmap: Optional[dict] = None
    coder_outputs: list = []
    test_reports: list = []
    human_requests: list = []
    started_at: str
    completed_at: Optional[str] = None

class StepOut(BaseModel):
    id: int
    run_id: int
    step_number: int
    step_type: str
    phase: str
    agent: str
    input: str
    output: Optional[str]
    latency_ms: int
    error: Optional[str]
    files_changed: Optional[str]
    git_commit: Optional[str]
    created_at: str

class SettingsResponse(BaseModel):
    working_dir: str
    ollama_endpoint: str
    ollama_api_key: str
    default_temperature: float

class SettingsUpdate(BaseModel):
    working_dir: Optional[str] = None
    ollama_endpoint: Optional[str] = None
    ollama_api_key: Optional[str] = None
    default_temperature: Optional[float] = None
