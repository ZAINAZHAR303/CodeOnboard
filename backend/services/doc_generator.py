import asyncio
import json
import logging
import posixpath
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from models.schemas import ApiEndpoint, FileInfo, FileMetrics, LearningStep, ModuleInfo
from services.llm_client import GeminiClient
from utils.file_helpers import is_code, is_test_file, tree_to_text, truncate

logger = logging.getLogger("codeonboard.docs")

SYSTEM_PROMPT = (
    "You are a staff engineer writing onboarding documentation for developers who are new to this repository. "
    "Only state facts that are supported by the repository context you are given. Reference real file and folder "
    "paths wrapped in backticks. Never invent files, functions or tools that are not in the context. "
    "Be concrete and specific to this codebase; avoid generic advice."
)


@dataclass
class RepoContext:
    repo_name: str
    tech_stack: list[str]
    patterns: dict[str, Any]
    entry_points: list[str]
    key_files: list[str]
    hotspots: list[dict[str, Any]]
    endpoints: list[ApiEndpoint]
    modules: list[ModuleInfo]
    file_tree: dict[str, Any]
    readme: str
    files: list[FileInfo]
    metrics: list[FileMetrics]
    by_path: dict[str, FileInfo] = field(init=False)

    def __post_init__(self) -> None:
        self.by_path = {f.path: f for f in self.files}

    def brief(self, include_contents: bool = True, content_budget: int = 40000) -> str:
        sections = [
            f"REPOSITORY: {self.repo_name}",
            f"TECH STACK: {', '.join(self.tech_stack) or 'unknown'}",
            f"DETECTED PATTERNS: {json.dumps(self.patterns)}",
            f"ENTRY POINTS: {', '.join(self.entry_points) or 'none detected'}",
            "MOST-IMPORTED FILES:\n" + ("\n".join(f"- {h['path']} (imported by {h['imported_by']} files)" for h in self.hotspots) or "- none detected"),
            "API ENDPOINTS:\n" + ("\n".join(f"- {e.method} {e.route}  ({e.file_path}:{e.line})" for e in self.endpoints[:40]) or "- none detected"),
            "MODULES:\n" + "\n".join(
                f"- {m.path} ({len(m.files)} files): {', '.join(posixpath.basename(p) for p in m.files[:12])}" for m in self.modules[:30]
            ),
            "FILE TREE:\n" + tree_to_text(self.file_tree, max_lines=250),
        ]
        if self.readme:
            sections.append("README (excerpt):\n" + truncate(self.readme, 5000))
        if include_contents:
            sections.append("KEY FILE CONTENTS:\n" + self.key_file_contents(content_budget))
        return "\n\n".join(sections)

    def key_file_contents(self, budget: int) -> str:
        chunks: list[str] = []
        used = 0
        for path in self.key_files:
            f = self.by_path.get(path)
            if not f or f.path.lower().startswith("readme"):
                continue
            snippet = truncate(f.content, 6000)
            if used + len(snippet) > budget:
                break
            chunks.append(f"--- {f.path} ---\n{snippet}")
            used += len(snippet)
        return "\n\n".join(chunks) or "(none)"

    def sample_files(self, count: int = 6) -> list[FileInfo]:
        metrics = {m.path: m for m in self.metrics}
        seen_modules: set[str] = set()
        picks: list[FileInfo] = []
        candidates = sorted(
            (f for f in self.files if is_code(f.language) and not is_test_file(f.path)),
            key=lambda f: -min(metrics[f.path].lines_of_code, 400) if f.path in metrics else 0,
        )
        for f in candidates:
            module = f.path.split("/")[0]
            if module in seen_modules:
                continue
            seen_modules.add(module)
            picks.append(f)
            if len(picks) >= count - 1:
                break
        test = next((f for f in self.files if is_test_file(f.path) and is_code(f.language)), None)
        if test:
            picks.append(test)
        return picks


ProgressCallback = Callable[[str, bool], Awaitable[None]]


class DocGenerator:
    def __init__(self, llm: GeminiClient) -> None:
        self.llm = llm

    async def generate_all(self, ctx: RepoContext, on_task_done: Optional[ProgressCallback] = None) -> dict[str, Any]:
        """Run the documentation agents concurrently; each falls back to structural output if the LLM fails."""
        brief = ctx.brief()
        tasks: dict[str, tuple[Callable[[], Awaitable[Any]], Callable[[], Any]]] = {
            "architecture": (lambda: self._architecture(brief), lambda: self._fallback_architecture(ctx)),
            "modules": (lambda: self._modules(ctx), lambda: self._fallback_modules(ctx)),
            "conventions": (lambda: self._conventions(ctx), lambda: self._fallback_conventions(ctx)),
            "how_to": (lambda: self._how_to(ctx, brief), lambda: self._fallback_how_to(ctx)),
            "learning_path": (lambda: self._learning_path(ctx, brief), lambda: self._fallback_learning_path(ctx)),
        }
        results: dict[str, Any] = {}
        warnings: list[str] = []

        async def run(name: str) -> None:
            primary, fallback = tasks[name]
            ok = True
            if self.llm.configured:
                try:
                    results[name] = await primary()
                except Exception as exc:  # any malformed model output should degrade to the fallback, not fail the job
                    logger.warning("Doc agent %s failed: %s", name, exc)
                    ok = False
            else:
                ok = False
            if not ok:
                results[name] = fallback()
                warnings.append(name)
            if on_task_done:
                await on_task_done(name, ok)

        await asyncio.gather(*(run(name) for name in tasks))
        results["warnings"] = warnings
        return results

    async def _architecture(self, brief: str) -> str:
        prompt = f"""{brief}

TASK: Write the "Architecture Overview" page of the onboarding guide for this repository, in GitHub-flavoured markdown.
Use exactly these sections (as ## headings):
## What this project does
## Architecture at a glance
  (include a small ASCII box-and-arrow diagram in a ```text code block showing the main components and how they connect)
## Key components
  (a bullet per important module/folder: `path/` - responsibility)
## How a request / data flows
  (numbered steps that trace one realistic flow through real files)
## Where to start reading
  (5-7 files in reading order, each with one sentence on why)

Keep it under 900 words. Do not wrap the whole answer in a code block."""
        text = await self.llm.generate(prompt, system=SYSTEM_PROMPT, temperature=0.3)
        return _strip_outer_fence(text)

    async def _modules(self, ctx: RepoContext) -> dict[str, Any]:
        listing = "\n".join(
            f"- {m.path} ({len(m.files)} files): {', '.join(m.files[:40])}" for m in ctx.modules[:30]
        )
        prompt = f"""{ctx.brief(content_budget=30000)}

MODULE LIST (path and files):
{listing}

TASK: For every module in MODULE LIST, write a 2-3 sentence description of its responsibility and how it relates to the rest
of the system, and pick up to 3 of its files that a newcomer should open first. Also propose 6 questions a new developer
would realistically ask about THIS codebase (mention real concepts/components from it).

Respond with JSON only:
{{"modules": [{{"path": "<module path exactly as listed>", "description": "...", "key_files": ["<file path>"]}}],
  "suggested_questions": ["..."]}}"""
        data = await self.llm.generate_json(prompt, system=SYSTEM_PROMPT, temperature=0.2)
        described = {item.get("path"): item for item in data.get("modules", []) if isinstance(item, dict)}
        modules: list[ModuleInfo] = []
        for m in ctx.modules:
            item = described.get(m.path) or described.get(m.name) or {}
            key_files = [p for p in item.get("key_files", []) if p in m.files][:3]
            modules.append(m.model_copy(update={
                "description": str(item.get("description") or self._module_fallback_text(m)),
                "key_files": key_files or m.files[:3],
            }))
        questions = [str(q) for q in data.get("suggested_questions", []) if isinstance(q, str)][:6]
        return {"modules": modules, "suggested_questions": questions or self._fallback_questions(ctx)}

    async def _conventions(self, ctx: RepoContext) -> str:
        samples = "\n\n".join(f"--- {f.path} ---\n{truncate(f.content, 3500)}" for f in ctx.sample_files())
        prompt = f"""REPOSITORY: {ctx.repo_name}
TECH STACK: {', '.join(ctx.tech_stack)}
DETECTED PATTERNS: {json.dumps(ctx.patterns)}

REPRESENTATIVE SOURCE FILES:
{samples}

TASK: Write the "Coding Conventions" page of the onboarding guide in markdown, based ONLY on evidence in the files above.
Use these ## sections: Naming, File & folder organisation, Error handling, Typing & documentation, Testing, Imports & dependencies.
Under each, give 2-4 bullets. Each bullet should cite the file it is based on in backticks, and where useful include a short
code example copied from the samples. End with a "## Checklist before opening a PR" section of 5-7 checkbox items (- [ ])."""
        return _strip_outer_fence(await self.llm.generate(prompt, system=SYSTEM_PROMPT, temperature=0.2))

    async def _how_to(self, ctx: RepoContext, brief: str) -> str:
        prompt = f"""{brief}

TASK: Write the "How to add a new feature" page of the onboarding guide in markdown.
1. Start with one sentence naming the most common kind of change in this repository (e.g. a new API endpoint, a new component,
   a new CLI command, a new plugin) based on the context.
2. Then give a numbered, step-by-step walkthrough for that change. Every step must name the exact existing file(s) to open or
   the folder where a new file should go, and follow the patterns those files already use. Include short code sketches that
   mirror the existing style.
3. Include steps for tests (where they live, how they are structured, how to run them) and for any registration/config/docs
   updates needed.
4. Finish with a "## Common pitfalls" section with 3-5 bullets specific to this codebase."""
        return _strip_outer_fence(await self.llm.generate(prompt, system=SYSTEM_PROMPT, temperature=0.3))

    async def _learning_path(self, ctx: RepoContext, brief: str) -> list[LearningStep]:
        prompt = f"""{brief}

TASK: Design a "first day" reading plan: an ordered list of 7-10 files a new developer should read to understand this
codebase, going from the big picture to the core logic to tests. Only use file paths that appear in the FILE TREE or context.
For each step give a short title, one or two sentences on what to look for in that file, and estimated reading minutes (3-30).

Respond with JSON only:
{{"steps": [{{"path": "...", "title": "...", "why": "...", "minutes": 10}}]}}"""
        data = await self.llm.generate_json(prompt, system=SYSTEM_PROMPT, temperature=0.2)
        steps: list[LearningStep] = []
        for item in data.get("steps", []):
            path = str(item.get("path", "")).strip().removeprefix("./").lstrip("/")
            if path not in ctx.by_path:
                continue
            steps.append(LearningStep(
                order=len(steps) + 1,
                path=path,
                title=str(item.get("title") or posixpath.basename(path)),
                why=str(item.get("why") or ""),
                minutes=max(1, min(60, int(item.get("minutes") or 10))),
            ))
        if len(steps) < 3:
            raise ValueError("learning path referenced too few real files")
        return steps

    def _module_fallback_text(self, m: ModuleInfo) -> str:
        exts = sorted({posixpath.splitext(p)[1] for p in m.files if posixpath.splitext(p)[1]})
        return f"Contains {len(m.files)} files ({', '.join(exts[:5]) or 'mixed'})."

    def _fallback_architecture(self, ctx: RepoContext) -> str:
        lines = [
            "## What this project does",
            f"`{ctx.repo_name}` is built with {', '.join(ctx.tech_stack) or 'an undetected stack'}. "
            f"Detected architecture style: **{ctx.patterns.get('architecture', 'unknown')}**.",
            "",
            "## Key components",
            *[f"- `{m.path}/` - {len(m.files)} files" for m in ctx.modules[:12]],
            "",
            "## Entry points",
            *([f"- `{p}`" for p in ctx.entry_points] or ["- none detected"]),
            "",
            "## Most-depended-on files",
            *([f"- `{h['path']}` - imported by {h['imported_by']} files" for h in ctx.hotspots[:8]] or ["- none detected"]),
            "",
            "> AI summary unavailable - this overview was generated from static analysis only.",
        ]
        return "\n".join(lines)

    def _fallback_modules(self, ctx: RepoContext) -> dict[str, Any]:
        modules = [m.model_copy(update={"description": self._module_fallback_text(m), "key_files": m.files[:3]}) for m in ctx.modules]
        return {"modules": modules, "suggested_questions": self._fallback_questions(ctx)}

    def _fallback_questions(self, ctx: RepoContext) -> list[str]:
        questions = ["How is this project structured, and what does each top-level folder do?"]
        if ctx.entry_points:
            questions.append(f"What happens when `{ctx.entry_points[0]}` runs?")
        if ctx.endpoints:
            questions.append("How do I add a new API endpoint?")
        if ctx.patterns.get("database"):
            questions.append(f"Where are the {ctx.patterns['database'][0]} models defined?")
        if ctx.patterns.get("testing"):
            questions.append(f"How are {ctx.patterns['testing'][0]} tests organised and how do I run them?")
        if ctx.hotspots:
            questions.append(f"Why do so many files import `{ctx.hotspots[0]['path']}`?")
        questions.append("What is the configuration and environment setup?")
        return questions[:6]

    def _fallback_conventions(self, ctx: RepoContext) -> str:
        lines = ["## Detected patterns"]
        for key, value in ctx.patterns.items():
            lines.append(f"- **{key.replace('_', ' ').title()}**: {', '.join(value) if isinstance(value, list) else value}")
        lines.append("\n> AI convention analysis unavailable - showing statically detected patterns only.")
        return "\n".join(lines)

    def _fallback_how_to(self, ctx: RepoContext) -> str:
        route_files = sorted({e.file_path for e in ctx.endpoints})[:5]
        tests = sorted({f.path.rsplit('/', 1)[0] for f in ctx.files if is_test_file(f.path) and '/' in f.path})[:3]
        lines = ["## Suggested workflow", "1. Read the entry points: " + (", ".join(f"`{p}`" for p in ctx.entry_points[:3]) or "n/a")]
        if route_files:
            lines.append("2. Add or extend a route in: " + ", ".join(f"`{p}`" for p in route_files))
        lines.append("3. Put business logic next to the most similar existing module (see Modules tab).")
        lines.append("4. Add tests in: " + (", ".join(f"`{t}/`" for t in tests) or "the project's test folder"))
        lines.append("\n> AI guide unavailable - this outline was generated from static analysis only.")
        return "\n".join(lines)

    def _fallback_learning_path(self, ctx: RepoContext) -> list[LearningStep]:
        return [
            LearningStep(order=i + 1, path=path, title=posixpath.basename(path), why="High-importance file (entry point, config, or widely imported).", minutes=10)
            for i, path in enumerate(ctx.key_files[:8])
        ]


def _strip_outer_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith(("```markdown", "```md", "```\n")) and stripped.endswith("```"):
        first_newline = stripped.find("\n")
        return stripped[first_newline + 1 : -3].strip()
    return stripped
