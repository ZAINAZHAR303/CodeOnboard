import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from config import settings
from models.schemas import FileInfo
from utils.file_helpers import (
    AUX_DIRS,
    IGNORED_DIRS,
    IGNORED_FILES,
    is_code,
    is_test_file,
    language_for,
    remove_dir,
    to_posix,
)

GITHUB_URL = re.compile(
    r"^https?://(?:www\.)?github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?(?:/tree/(?P<branch>[^?#]+))?/?(?:[?#].*)?$"
)
SAFE_BRANCH = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")


class IngestError(ValueError):
    pass


@dataclass
class RepoRef:
    owner: str
    repo: str
    branch: Optional[str]

    @property
    def clone_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}.git"

    @property
    def web_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}"

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"


@dataclass
class IngestedRepo:
    ref: RepoRef
    path: Path
    all_paths: list[str]
    files: list[FileInfo]
    tech_stack: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    readme: str = ""


def parse_github_url(url: str, branch: Optional[str] = None) -> RepoRef:
    match = GITHUB_URL.match(url.strip())
    if not match:
        raise IngestError("Please enter a public GitHub repository URL like https://github.com/owner/repo")
    chosen_branch = (branch or match.group("branch") or "").strip() or None
    if chosen_branch and (not SAFE_BRANCH.match(chosen_branch) or chosen_branch.startswith("-")):
        raise IngestError("Invalid branch name")
    return RepoRef(match.group("owner"), match.group("repo"), chosen_branch)


class RepoIngester:
    def clone_repo(self, ref: RepoRef) -> Path:
        settings.clone_dir.mkdir(parents=True, exist_ok=True)
        dest = settings.clone_dir / f"{ref.owner}__{ref.repo}__{int(time.time() * 1000)}"
        cmd = ["git", "clone", "--depth", "1", "--single-branch"]
        if ref.branch:
            cmd += ["--branch", ref.branch]
        cmd += ["--", ref.clone_url, str(dest)]

        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=settings.clone_timeout_seconds, env=env
            )
        except subprocess.TimeoutExpired as exc:
            remove_dir(dest)
            raise IngestError("Cloning timed out - the repository may be too large") from exc

        if result.returncode != 0:
            remove_dir(dest)
            stderr = result.stderr.lower()
            if "not found" in stderr or "authentication" in stderr or "could not read username" in stderr:
                raise IngestError("Repository not found or it is private. Only public repositories are supported.")
            if "remote branch" in stderr and "not found" in stderr:
                raise IngestError(f"Branch '{ref.branch}' does not exist in this repository")
            raise IngestError(f"git clone failed: {result.stderr.strip()[:300]}")
        return dest

    def list_paths(self, repo_path: Path) -> list[str]:
        paths: list[str] = []
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".") or d in {".github"}]
            for name in files:
                if name in IGNORED_FILES or name.endswith((".pyc", ".pyo", ".min.js", ".min.css", ".map")):
                    continue
                paths.append(to_posix(Path(root) / name, repo_path))
        return sorted(paths)

    def read_source_files(self, repo_path: Path, paths: list[str]) -> list[FileInfo]:
        candidates: list[tuple[int, str, str]] = []
        for rel in paths:
            language = language_for(rel)
            if not language:
                continue
            priority = 0 if is_code(language) and not is_test_file(rel) else 1 if is_code(language) else 2
            candidates.append((priority, rel, language))
        candidates.sort(key=lambda item: (item[0], item[1].count("/"), item[1]))

        files: list[FileInfo] = []
        for _, rel, language in candidates[: settings.max_files]:
            full = repo_path / rel
            try:
                size = full.stat().st_size
                if size == 0 or size > settings.max_file_bytes:
                    continue
                raw = full.read_bytes()
            except OSError:
                continue
            if b"\x00" in raw[:4096]:
                continue
            content = raw.decode("utf-8", errors="replace")
            files.append(FileInfo(path=rel, content=content, language=language, size=size))
        files.sort(key=lambda f: f.path)
        return files

    def detect_tech_stack(self, files: list[FileInfo], paths: list[str]) -> list[str]:
        stack: list[str] = []

        def add(name: str) -> None:
            if name not in stack:
                stack.append(name)

        by_path = {f.path: f.content for f in files}
        languages: dict[str, int] = {}
        for f in files:
            if is_code(f.language):
                languages[f.language] = languages.get(f.language, 0) + 1
        for lang, _ in sorted(languages.items(), key=lambda kv: -kv[1])[:4]:
            add(lang)

        for path, content in by_path.items():
            if set(path.lower().split("/")[:-1]) & AUX_DIRS:
                continue
            name = path.rsplit("/", 1)[-1]
            if name == "package.json":
                try:
                    pkg = json.loads(content)
                except json.JSONDecodeError:
                    continue
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                add("Node.js")
                for dep, label in NPM_FRAMEWORKS.items():
                    if dep in deps:
                        add(label)
            elif name in {"requirements.txt", "pyproject.toml", "Pipfile", "setup.py", "setup.cfg"}:
                lowered = content.lower()
                for dep, label in PY_FRAMEWORKS.items():
                    if re.search(rf"(^|[\s\"'\[,]){re.escape(dep)}([\s\"'=<>~!\[,;]|$)", lowered, re.MULTILINE):
                        add(label)
            elif name in {"pom.xml", "build.gradle", "build.gradle.kts"}:
                add("Maven" if name == "pom.xml" else "Gradle")
                if "spring-boot" in content or "org.springframework" in content:
                    add("Spring Boot")
            elif name == "go.mod":
                for dep, label in GO_FRAMEWORKS.items():
                    if dep in content:
                        add(label)
            elif name == "Cargo.toml":
                for dep in ("actix-web", "axum", "rocket", "tokio"):
                    if re.search(rf"^{dep}\s*=", content, re.MULTILINE):
                        add(dep.capitalize())
            elif name == "Gemfile" and "rails" in content:
                add("Ruby on Rails")
            elif name == "composer.json" and "laravel" in content:
                add("Laravel")

        joined = "\n".join(paths)
        if re.search(r"(^|/)Dockerfile", joined, re.MULTILINE):
            add("Docker")
        if re.search(r"(^|/)(docker-)?compose\.ya?ml$", joined, re.MULTILINE):
            add("Docker Compose")
        if ".github/workflows/" in joined:
            add("GitHub Actions")
        if re.search(r"\.tf$", joined, re.MULTILINE):
            add("Terraform")
        if re.search(r"(^|/)(k8s|kubernetes|helm)/", joined, re.MULTILINE):
            add("Kubernetes")
        return stack

    def find_entry_points(self, paths: list[str], files: list[FileInfo]) -> list[str]:
        found = [p for p in paths if p.rsplit("/", 1)[-1] in ENTRY_POINT_NAMES and p.count("/") <= 3 and not is_test_file(p)]
        for f in files:
            if f.language == "Python" and 'if __name__ == "__main__"' in f.content and f.path not in found and not is_test_file(f.path):
                found.append(f.path)
            if f.path.rsplit("/", 1)[-1] == "package.json" and f.path.count("/") <= 1:
                try:
                    main = json.loads(f.content).get("main")
                except json.JSONDecodeError:
                    main = None
                if isinstance(main, str):
                    base = f.path.rsplit("/", 1)[0] + "/" if "/" in f.path else ""
                    candidate = (base + main.lstrip("./")).replace("//", "/")
                    if candidate in paths and candidate not in found:
                        found.append(candidate)
        found.sort(key=lambda p: (p.count("/"), p))
        return found[:12]

    def find_readme(self, files: list[FileInfo]) -> str:
        for f in files:
            if "/" not in f.path and f.path.lower().startswith("readme"):
                return f.content
        return ""

    def ingest(self, ref: RepoRef) -> IngestedRepo:
        path = self.clone_repo(ref)
        paths = self.list_paths(path)
        files = self.read_source_files(path, paths)
        if not files:
            remove_dir(path)
            raise IngestError("No readable source files found in this repository")
        return IngestedRepo(
            ref=ref,
            path=path,
            all_paths=paths,
            files=files,
            tech_stack=self.detect_tech_stack(files, paths),
            entry_points=self.find_entry_points(paths, files),
            readme=self.find_readme(files),
        )

    def cleanup(self, repo_path: Path) -> None:
        remove_dir(repo_path)


ENTRY_POINT_NAMES = {
    "main.py", "app.py", "wsgi.py", "asgi.py", "manage.py", "__main__.py", "server.py", "cli.py",
    "index.js", "index.ts", "index.jsx", "index.tsx", "main.js", "main.ts", "main.jsx", "main.tsx", "server.js", "server.ts",
    "app.js", "app.ts", "App.jsx", "App.tsx", "App.vue", "main.go", "Main.java", "Application.java", "Program.cs",
    "main.rs", "lib.rs", "main.dart", "index.php",
}

NPM_FRAMEWORKS = {
    "react": "React", "next": "Next.js", "vue": "Vue", "nuxt": "Nuxt", "@angular/core": "Angular", "svelte": "Svelte",
    "@sveltejs/kit": "SvelteKit", "express": "Express", "fastify": "Fastify", "koa": "Koa", "@nestjs/core": "NestJS",
    "vite": "Vite", "webpack": "Webpack", "tailwindcss": "Tailwind CSS", "redux": "Redux", "@reduxjs/toolkit": "Redux",
    "prisma": "Prisma", "@prisma/client": "Prisma", "mongoose": "MongoDB", "typeorm": "TypeORM", "sequelize": "Sequelize",
    "graphql": "GraphQL", "jest": "Jest", "vitest": "Vitest", "mocha": "Mocha", "cypress": "Cypress",
    "@playwright/test": "Playwright", "electron": "Electron", "react-native": "React Native", "socket.io": "Socket.IO",
    "typescript": "TypeScript",
}

PY_FRAMEWORKS = {
    "django": "Django", "flask": "Flask", "fastapi": "FastAPI", "starlette": "Starlette", "sqlalchemy": "SQLAlchemy",
    "pydantic": "Pydantic", "celery": "Celery", "pytest": "pytest", "pandas": "pandas", "numpy": "NumPy",
    "torch": "PyTorch", "tensorflow": "TensorFlow", "scikit-learn": "scikit-learn", "langchain": "LangChain",
    "streamlit": "Streamlit", "werkzeug": "Werkzeug", "jinja2": "Jinja2", "click": "Click", "aiohttp": "aiohttp",
    "tornado": "Tornado", "alembic": "Alembic", "redis": "Redis", "psycopg2": "PostgreSQL", "pymongo": "MongoDB",
}

GO_FRAMEWORKS = {"gin-gonic/gin": "Gin", "labstack/echo": "Echo", "gofiber/fiber": "Fiber", "gorm.io": "GORM", "go-chi/chi": "Chi"}
