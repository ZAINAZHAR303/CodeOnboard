from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class FileInfo(BaseModel):
    path: str
    content: str
    language: str
    size: int


class ModuleInfo(BaseModel):
    name: str
    path: str
    description: str = ""
    files: list[str] = Field(default_factory=list)
    key_files: list[str] = Field(default_factory=list)


class DependencyEdge(BaseModel):
    source: str
    target: str
    import_type: str = "direct"


class FileMetrics(BaseModel):
    path: str
    language: str
    lines_of_code: int
    num_functions: int
    num_classes: int
    num_imports: int
    is_test: bool = False


class ApiEndpoint(BaseModel):
    file_path: str
    method: str
    route: str
    framework: str
    line: int = 0


class LearningStep(BaseModel):
    order: int
    path: str
    title: str
    why: str
    minutes: int = 10


class RepoStats(BaseModel):
    total_files: int = 0
    analyzed_files: int = 0
    total_lines: int = 0
    languages: dict[str, int] = Field(default_factory=dict)
    test_files: int = 0
    analysis_seconds: float = 0.0


class AnalysisResult(BaseModel):
    repo_id: str
    repo_name: str
    repo_url: str
    branch: Optional[str] = None
    created_at: str
    tech_stack: list[str] = Field(default_factory=list)
    architecture_summary: str = ""
    modules: list[ModuleInfo] = Field(default_factory=list)
    dependencies: list[DependencyEdge] = Field(default_factory=list)
    entry_points: list[str] = Field(default_factory=list)
    key_files: list[str] = Field(default_factory=list)
    hotspots: list[dict[str, Any]] = Field(default_factory=list)
    conventions: str = ""
    how_to_add_feature: str = ""
    learning_path: list[LearningStep] = Field(default_factory=list)
    suggested_questions: list[str] = Field(default_factory=list)
    api_endpoints: list[ApiEndpoint] = Field(default_factory=list)
    patterns: dict[str, Any] = Field(default_factory=dict)
    file_metrics: list[FileMetrics] = Field(default_factory=list)
    file_tree: dict[str, Any] = Field(default_factory=dict)
    stats: RepoStats = Field(default_factory=RepoStats)
    ai_generated: bool = True
    warnings: list[str] = Field(default_factory=list)


class AnalysisSummary(BaseModel):
    repo_id: str
    repo_name: str
    repo_url: str
    branch: Optional[str] = None
    created_at: str
    tech_stack: list[str]
    total_files: int


class AnalyzeRequest(BaseModel):
    repo_url: str
    branch: Optional[str] = None
    force: bool = False


class JobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    stage: str = ""
    progress: int = 0
    message: str = ""
    repo_id: Optional[str] = None
    error: Optional[str] = None
    log: list[str] = Field(default_factory=list)


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    repo_id: str
    question: str = Field(min_length=1, max_length=4000)
    history: list[ChatTurn] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str
    relevant_files: list[str] = Field(default_factory=list)


class TicketMapRequest(BaseModel):
    repo_id: str
    ticket_description: str = Field(min_length=5, max_length=6000)


class MappedFile(BaseModel):
    path: str
    reason: str
    relevance_score: float
    change_type: Literal["modify", "create", "review"] = "modify"
    exists: bool = True


class TicketMapResponse(BaseModel):
    summary: str = ""
    relevant_files: list[MappedFile] = Field(default_factory=list)
    suggested_tests: list[str] = Field(default_factory=list)
    related_apis: list[str] = Field(default_factory=list)
    implementation_steps: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    estimated_effort: str = ""
