import json
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from config import settings
from models.schemas import AnalysisResult, AnalysisSummary, FileInfo
from services.retrieval import FileRetriever

SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")


@dataclass
class Workspace:
    analysis: AnalysisResult
    files: list[FileInfo]
    by_path: dict[str, FileInfo] = field(init=False)
    _retriever: Optional[FileRetriever] = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.by_path = {f.path: f for f in self.files}

    @property
    def retriever(self) -> FileRetriever:
        if self._retriever is None:
            self._retriever = FileRetriever(self.files)
        return self._retriever

    def file_index(self, max_lines: int = 1200) -> str:
        module_of = {p: m.path for m in self.analysis.modules for p in m.files}
        metrics = {m.path: m for m in self.analysis.file_metrics}
        endpoint_count: dict[str, int] = {}
        for e in self.analysis.api_endpoints:
            endpoint_count[e.file_path] = endpoint_count.get(e.file_path, 0) + 1
        lines = []
        for f in self.files[:max_lines]:
            tags = []
            if f.path in module_of:
                tags.append(f"module={module_of[f.path]}")
            m = metrics.get(f.path)
            if m:
                tags.append(f"{m.lines_of_code} loc")
                if m.is_test:
                    tags.append("test")
            if f.path in endpoint_count:
                tags.append(f"{endpoint_count[f.path]} endpoints")
            lines.append(f"{f.path} [{', '.join(tags)}]" if tags else f.path)
        return "\n".join(lines)


class AnalysisStore:
    def __init__(self, root: Path | None = None, cache_size: int = 6) -> None:
        self.root = root or settings.data_dir / "analyses"
        self.root.mkdir(parents=True, exist_ok=True)
        self._cache: OrderedDict[str, Workspace] = OrderedDict()
        self._cache_size = cache_size
        self._lock = threading.Lock()

    def _dir(self, repo_id: str) -> Path:
        if not SAFE_ID.match(repo_id):
            raise KeyError(repo_id)
        return self.root / repo_id

    def save(self, analysis: AnalysisResult, files: list[FileInfo]) -> None:
        directory = self._dir(analysis.repo_id)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "analysis.json").write_text(analysis.model_dump_json(), encoding="utf-8")
        (directory / "files.json").write_text(json.dumps([f.model_dump() for f in files]), encoding="utf-8")
        with self._lock:
            self._remember(analysis.repo_id, Workspace(analysis=analysis, files=files))

    def get(self, repo_id: str) -> Workspace:
        with self._lock:
            if repo_id in self._cache:
                self._cache.move_to_end(repo_id)
                return self._cache[repo_id]
        directory = self._dir(repo_id)
        analysis_file = directory / "analysis.json"
        if not analysis_file.exists():
            raise KeyError(repo_id)
        analysis = AnalysisResult.model_validate_json(analysis_file.read_text(encoding="utf-8"))
        files = [FileInfo(**item) for item in json.loads((directory / "files.json").read_text(encoding="utf-8"))]
        workspace = Workspace(analysis=analysis, files=files)
        with self._lock:
            self._remember(repo_id, workspace)
        return workspace

    def _remember(self, repo_id: str, workspace: Workspace) -> None:
        self._cache[repo_id] = workspace
        self._cache.move_to_end(repo_id)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    def list(self) -> list[AnalysisSummary]:
        summaries: list[AnalysisSummary] = []
        for analysis_file in self.root.glob("*/analysis.json"):
            try:
                data = json.loads(analysis_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            summaries.append(AnalysisSummary(
                repo_id=data["repo_id"],
                repo_name=data["repo_name"],
                repo_url=data["repo_url"],
                branch=data.get("branch"),
                created_at=data["created_at"],
                tech_stack=data.get("tech_stack", [])[:6],
                total_files=data.get("stats", {}).get("analyzed_files", 0),
            ))
        summaries.sort(key=lambda s: s.created_at, reverse=True)
        return summaries

    def find_existing(self, repo_url: str, branch: Optional[str]) -> Optional[str]:
        for summary in self.list():
            if summary.repo_url.lower() == repo_url.lower() and (summary.branch or None) == (branch or None):
                return summary.repo_id
        return None
