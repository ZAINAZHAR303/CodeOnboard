import os
import re
import shutil
import stat
from pathlib import Path, PurePosixPath
from typing import Any

IGNORED_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv", "env", "dist", "build",
    ".next", ".nuxt", ".svelte-kit", ".cache", ".idea", ".vscode", ".pytest_cache", ".mypy_cache",
    ".tox", "coverage", ".gradle", "target", "bin", "obj", "vendor", "bower_components", ".terraform",
    "site-packages", ".eggs", "htmlcov", ".turbo", ".parcel-cache", "out",
}

AUX_DIRS = {"test", "tests", "__tests__", "spec", "specs", "e2e", "examples", "example", "docs", "doc", "benchmarks", "bench", "scripts", ".github"}

IGNORED_FILES = {".DS_Store", "Thumbs.db", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Cargo.lock", "composer.lock", "Gemfile.lock", "go.sum"}

LANGUAGE_BY_EXT = {
    ".py": "Python", ".pyi": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin", ".scala": "Scala",
    ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".php": "PHP", ".c": "C", ".h": "C", ".cpp": "C++", ".cc": "C++",
    ".hpp": "C++", ".cs": "C#", ".swift": "Swift", ".vue": "Vue", ".svelte": "Svelte", ".html": "HTML",
    ".css": "CSS", ".scss": "SCSS", ".sass": "SCSS", ".less": "CSS", ".sql": "SQL", ".sh": "Shell", ".bash": "Shell",
    ".ps1": "PowerShell", ".yaml": "YAML", ".yml": "YAML", ".json": "JSON", ".toml": "TOML", ".ini": "Config",
    ".cfg": "Config", ".md": "Markdown", ".rst": "reStructuredText", ".txt": "Text", ".xml": "XML", ".gradle": "Gradle",
    ".dart": "Dart", ".ex": "Elixir", ".exs": "Elixir", ".lua": "Lua", ".r": "R", ".proto": "Protobuf", ".graphql": "GraphQL",
}

SPECIAL_FILENAMES = {"Dockerfile": "Docker", "Makefile": "Make", "Procfile": "Config", "Jenkinsfile": "Groovy", "Gemfile": "Ruby", "Rakefile": "Ruby"}

CODE_LANGUAGES = {
    "Python", "JavaScript", "TypeScript", "Java", "Kotlin", "Scala", "Go", "Rust", "Ruby", "PHP", "C", "C++", "C#",
    "Swift", "Vue", "Svelte", "Dart", "Elixir", "Lua", "R", "Shell", "SQL",
}

TEST_PATTERN = re.compile(
    r"(^|/)(tests?|__tests__|spec|specs)/|(^|/)test_[^/]+\.py$|_test\.(py|go)$|\.(test|spec)\.[jt]sx?$|Tests?\.(java|kt|cs)$"
)


def language_for(path: str) -> str | None:
    name = PurePosixPath(path).name
    if name in SPECIAL_FILENAMES:
        return SPECIAL_FILENAMES[name]
    return LANGUAGE_BY_EXT.get(PurePosixPath(path).suffix.lower())


def is_test_file(path: str) -> bool:
    return bool(TEST_PATTERN.search(path))


def is_code(language: str) -> bool:
    return language in CODE_LANGUAGES


def to_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def build_tree(paths: list[str]) -> dict[str, Any]:
    tree: dict[str, Any] = {}
    for path in sorted(paths):
        node = tree
        parts = path.split("/")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
            if node is None:
                break
        else:
            node[parts[-1]] = None
    return tree


def tree_to_text(tree: dict[str, Any], max_lines: int = 300) -> str:
    lines: list[str] = []

    def walk(node: dict[str, Any], depth: int) -> None:
        dirs = sorted(k for k, v in node.items() if isinstance(v, dict))
        files = sorted(k for k, v in node.items() if v is None)
        for name in dirs:
            if len(lines) >= max_lines:
                return
            lines.append(f"{'  ' * depth}{name}/")
            walk(node[name], depth + 1)
        shown = files if len(files) <= 25 else files[:25]
        for name in shown:
            if len(lines) >= max_lines:
                return
            lines.append(f"{'  ' * depth}{name}")
        if len(files) > len(shown):
            lines.append(f"{'  ' * depth}... ({len(files) - len(shown)} more files)")

    walk(tree, 0)
    if len(lines) >= max_lines:
        lines.append("... (tree truncated)")
    return "\n".join(lines)


def _force_remove(func, path, _exc_info) -> None:
    os.chmod(path, stat.S_IWRITE)
    func(path)


def remove_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, onerror=_force_remove)


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated {len(text) - limit} chars]"
