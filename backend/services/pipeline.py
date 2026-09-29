import asyncio
import hashlib
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from models.schemas import AnalysisResult, JobStatus, RepoStats
from services.code_analyzer import CodeAnalyzer
from services.doc_generator import DocGenerator, RepoContext
from services.repo_ingester import IngestError, RepoIngester, RepoRef
from services.store import AnalysisStore
from utils.file_helpers import build_tree, is_code, is_test_file

logger = logging.getLogger("codeonboard.pipeline")

AGENT_LABELS = {
    "architecture": "Architecture agent finished",
    "modules": "Module agent finished",
    "conventions": "Conventions agent finished",
    "how_to": "How-to agent finished",
    "learning_path": "Learning-path agent finished",
}


class JobManager:
    def __init__(self, store: AnalysisStore, ingester: RepoIngester, analyzer: CodeAnalyzer, docs: DocGenerator) -> None:
        self.store = store
        self.ingester = ingester
        self.analyzer = analyzer
        self.docs = docs
        self.jobs: dict[str, JobStatus] = {}
        self._tasks: set[asyncio.Task] = set()

    def start(self, ref: RepoRef) -> JobStatus:
        job = JobStatus(job_id=uuid.uuid4().hex[:12], status="queued", stage="queued", message="Waiting to start")
        self.jobs[job.job_id] = job
        task = asyncio.create_task(self._run(job, ref))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job

    def get(self, job_id: str) -> Optional[JobStatus]:
        return self.jobs.get(job_id)

    def _update(self, job: JobStatus, stage: str, progress: int, message: str) -> None:
        job.stage, job.progress, job.message = stage, progress, message
        job.log.append(message)

    async def _run(self, job: JobStatus, ref: RepoRef) -> None:
        started = time.perf_counter()
        job.status = "running"
        repo = None
        try:
            self._update(job, "cloning", 5, f"Cloning {ref.full_name}{' @ ' + ref.branch if ref.branch else ''}")
            repo = await asyncio.to_thread(self.ingester.ingest, ref)
            self._update(job, "scanning", 25, f"Read {len(repo.files)} source files out of {len(repo.all_paths)} total")

            files = repo.files
            self._update(job, "analyzing", 32, "Building dependency graph and detecting patterns")
            dependencies, modules, metrics, endpoints, patterns = await asyncio.to_thread(self._static_analysis, files, repo.all_paths)
            hotspots = self.analyzer.compute_hotspots(dependencies)
            key_files = self.analyzer.get_key_files(files, repo.entry_points, hotspots, endpoints)
            file_tree = build_tree(repo.all_paths)
            self._update(
                job, "analyzing", 45,
                f"Found {len(modules)} modules, {len(dependencies)} internal imports, {len(endpoints)} API endpoints",
            )

            ctx = RepoContext(
                repo_name=ref.full_name, tech_stack=repo.tech_stack, patterns=patterns, entry_points=repo.entry_points,
                key_files=key_files, hotspots=hotspots, endpoints=endpoints, modules=modules, file_tree=file_tree,
                readme=repo.readme, files=files, metrics=metrics,
            )
            done = 0
            self._update(job, "generating", 50, "Launching 5 documentation agents in parallel")

            async def on_done(name: str, ok: bool) -> None:
                nonlocal done
                done += 1
                suffix = "" if ok else " (used static fallback)"
                self._update(job, "generating", 50 + done * 9, f"{AGENT_LABELS[name]}{suffix} [{done}/5]")

            docs = await self.docs.generate_all(ctx, on_done)

            self._update(job, "saving", 97, "Saving onboarding package")
            languages: dict[str, int] = {}
            for f in files:
                if is_code(f.language):
                    languages[f.language] = languages.get(f.language, 0) + 1
            repo_id = f"{ref.owner}-{ref.repo}-{hashlib.sha1(f'{ref.web_url}|{ref.branch}|{time.time()}'.encode()).hexdigest()[:6]}".lower()
            analysis = AnalysisResult(
                repo_id=repo_id,
                repo_name=ref.full_name,
                repo_url=ref.web_url,
                branch=ref.branch,
                created_at=datetime.now(timezone.utc).isoformat(),
                tech_stack=repo.tech_stack,
                architecture_summary=docs["architecture"],
                modules=docs["modules"]["modules"],
                suggested_questions=docs["modules"]["suggested_questions"],
                dependencies=dependencies,
                entry_points=repo.entry_points,
                key_files=key_files,
                hotspots=hotspots,
                conventions=docs["conventions"],
                how_to_add_feature=docs["how_to"],
                learning_path=docs["learning_path"],
                api_endpoints=endpoints,
                patterns=patterns,
                file_metrics=metrics,
                file_tree=file_tree,
                stats=RepoStats(
                    total_files=len(repo.all_paths),
                    analyzed_files=len(files),
                    total_lines=sum(m.lines_of_code for m in metrics),
                    languages=dict(sorted(languages.items(), key=lambda kv: -kv[1])),
                    test_files=sum(1 for f in files if is_test_file(f.path)),
                    analysis_seconds=round(time.perf_counter() - started, 1),
                ),
                ai_generated=len(docs["warnings"]) < 5,
                warnings=[f"{name.replace('_', ' ')} section used static fallback" for name in docs["warnings"]],
            )
            await asyncio.to_thread(self.store.save, analysis, files)
            job.repo_id = repo_id
            job.status = "completed"
            self._update(job, "done", 100, f"Onboarding package ready in {analysis.stats.analysis_seconds}s")
        except IngestError as exc:
            job.status, job.error = "failed", str(exc)
            self._update(job, "failed", job.progress, str(exc))
        except Exception as exc:
            logger.exception("Analysis job %s failed", job.job_id)
            job.status, job.error = "failed", f"Unexpected error: {exc}"
            self._update(job, "failed", job.progress, job.error)
        finally:
            if repo is not None:
                await asyncio.to_thread(self.ingester.cleanup, repo.path)

    def _static_analysis(self, files, all_paths):
        dependencies = self.analyzer.analyze_dependencies(files)
        modules = self.analyzer.identify_modules(files)
        metrics = self.analyzer.analyze_file_complexity(files)
        endpoints = self.analyzer.extract_api_endpoints(files)
        patterns = self.analyzer.detect_patterns(files, all_paths)
        return dependencies, modules, metrics, endpoints, patterns
