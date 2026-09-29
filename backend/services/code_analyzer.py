import posixpath
import re
from collections import Counter, defaultdict
from typing import Any

from models.schemas import ApiEndpoint, DependencyEdge, FileInfo, FileMetrics, ModuleInfo
from utils.file_helpers import AUX_DIRS, is_code, is_test_file

PY_IMPORT = re.compile(r"^\s*import\s+([\w.]+(?:\s*,\s*[\w.]+)*)", re.MULTILINE)
PY_FROM = re.compile(r"^\s*from\s+(\.*[\w.]*)\s+import\s+\(?\s*([\w\s,.*]+)", re.MULTILINE)
JS_IMPORT = re.compile(
    r"""(?:import\s+(?:[\w*{}\s,]+\s+from\s+)?|export\s+[\w*{}\s,]+\s+from\s+|require\(\s*|import\(\s*)['"]([^'"]+)['"]"""
)
JAVA_IMPORT = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)\s*;", re.MULTILINE)
JAVA_PACKAGE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)
C_INCLUDE = re.compile(r'^\s*#include\s+"([^"]+)"', re.MULTILINE)

JS_EXTS = [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte"]
FUNC_PATTERNS = {
    "Python": re.compile(r"^\s*(?:async\s+)?def\s+\w+", re.MULTILINE),
    "JavaScript": re.compile(r"\bfunction\b\s*\w*\s*\(|(?:const|let|var)\s+\w+\s*=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>|^\s*(?:async\s+)?(?!(?:if|for|while|switch|catch|return)\b)\w+\s*\([^)]*\)\s*\{", re.MULTILINE),
    "Java": re.compile(r"^\s*(?:(?:public|private|protected|static|final|synchronized|abstract)\s+)+[\w<>\[\].?,]+\s+\w+\s*\(", re.MULTILINE),
    "Go": re.compile(r"^func\s", re.MULTILINE),
    "Rust": re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+\w+", re.MULTILINE),
    "Ruby": re.compile(r"^\s*def\s+\w+", re.MULTILINE),
    "PHP": re.compile(r"\bfunction\s+\w+\s*\(", re.MULTILINE),
}
FUNC_PATTERNS["TypeScript"] = FUNC_PATTERNS["JavaScript"]
FUNC_PATTERNS["Kotlin"] = re.compile(r"^\s*(?:\w+\s+)*fun\s+\w+", re.MULTILINE)
CLASS_PATTERN = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:public\s+|abstract\s+|final\s+|data\s+)*(?:class|interface|struct|enum|trait)\s+\w+", re.MULTILINE)
COMMENT_PREFIXES = ("#", "//", "/*", "*", "--", '"""', "'''")

HTTP_METHODS = "get|post|put|patch|delete|options|head|all"
ENDPOINT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("FastAPI/Flask", re.compile(rf"@\w+\.({HTTP_METHODS}|websocket)\(\s*[rf]?['\"]([^'\"]*)['\"]", re.IGNORECASE)),
    ("Flask", re.compile(r"@\w+\.route\(\s*['\"]([^'\"]*)['\"](?:[^)]*methods\s*=\s*\[([^\]]*)\])?")),
    ("Express", re.compile(rf"\b(?:app|router|server|api|routes?)\.({HTTP_METHODS})\(\s*['\"`]([^'\"`]+)['\"`]")),
    ("Django", re.compile(r"\b(?:re_)?path\(\s*r?['\"]([^'\"]*)['\"]\s*,\s*([\w.]+)")),
    ("Spring", re.compile(r"@(Get|Post|Put|Delete|Patch|Request)Mapping\(\s*(?:value\s*=\s*|path\s*=\s*)?\"([^\"]*)\"")),
    ("NestJS", re.compile(r"@(Get|Post|Put|Delete|Patch)\(\s*['\"]([^'\"]*)['\"]\s*\)")),
]


class CodeAnalyzer:
    def __init__(self) -> None:
        self._py_names: dict[str, str] = {}

    def analyze_dependencies(self, files: list[FileInfo]) -> list[DependencyEdge]:
        paths = {f.path for f in files}
        py_index, self._py_names = self._python_module_index(files)
        java_index = self._java_class_index(files)
        edges: dict[tuple[str, str], DependencyEdge] = {}

        def add(source: str, target: str | None, kind: str) -> None:
            if target and target != source and target in paths:
                edges.setdefault((source, target), DependencyEdge(source=source, target=target, import_type=kind))

        for f in files:
            if f.language == "Python":
                for target, kind in self._python_imports(f, py_index):
                    add(f.path, target, kind)
            elif f.language in {"JavaScript", "TypeScript", "Vue", "Svelte"}:
                for spec in JS_IMPORT.findall(f.content):
                    add(f.path, self._resolve_js(f.path, spec, paths), "relative" if spec.startswith(".") else "alias")
            elif f.language in {"Java", "Kotlin"}:
                for fqn in JAVA_IMPORT.findall(f.content):
                    add(f.path, java_index.get(fqn), "direct")
            elif f.language in {"C", "C++"}:
                directory = posixpath.dirname(f.path)
                for inc in C_INCLUDE.findall(f.content):
                    candidate = posixpath.normpath(posixpath.join(directory, inc))
                    add(f.path, candidate if candidate in paths else self._by_suffix(inc, paths), "direct")
        return list(edges.values())

    def _python_module_index(self, files: list[FileInfo]) -> tuple[dict[str, str], dict[str, str]]:
        py_paths = {f.path for f in files if f.path.endswith(".py")}
        packages = {posixpath.dirname(p) for p in py_paths if p.endswith("__init__.py")}
        index: dict[str, str] = {}
        names: dict[str, str] = {}
        for path in sorted(py_paths, key=lambda p: p.count("/")):
            parts = path[:-3].split("/")
            is_init = parts[-1] == "__init__"
            if is_init:
                parts = parts[:-1]
            directory = posixpath.dirname(path)
            start = len(directory.split("/")) if directory else 0
            while start > 0 and "/".join(path.split("/")[:start]) in packages:
                start -= 1
            dotted = ".".join(parts[start:])
            names[path] = dotted
            if dotted:
                index.setdefault(dotted, path)
            full = ".".join(parts)
            if full:
                index.setdefault(full, path)
        return index, names

    def _python_package_of(self, path: str) -> str:
        dotted = self._py_names.get(path, "")
        if path.endswith("__init__.py"):
            return dotted
        return dotted.rsplit(".", 1)[0] if "." in dotted else ""

    def _python_imports(self, f: FileInfo, index: dict[str, str]) -> list[tuple[str, str]]:
        results: list[tuple[str, str]] = []
        for group in PY_IMPORT.findall(f.content):
            for name in (n.strip() for n in group.split(",")):
                target = self._lookup_py(name, index)
                if target:
                    results.append((target, "direct"))

        package = self._python_package_of(f.path)
        for module, names in PY_FROM.findall(f.content):
            imported = [n.strip().split(" as ")[0] for n in names.replace("\n", " ").split(",") if n.strip() and n.strip() != "*"]
            if module.startswith("."):
                level = len(module) - len(module.lstrip("."))
                base_parts = package.split(".") if package else []
                if level > 1:
                    base_parts = base_parts[: len(base_parts) - (level - 1)]
                rest = module.lstrip(".")
                base = ".".join([*base_parts, rest] if rest else base_parts)
                kind = "relative"
            else:
                base = module
                kind = "direct"
            matched = False
            for name in imported:
                target = self._lookup_py(f"{base}.{name}" if base else name, index)
                if target:
                    results.append((target, kind))
                    matched = True
            if not matched and base:
                target = self._lookup_py(base, index)
                if target:
                    results.append((target, kind))
        return results

    @staticmethod
    def _lookup_py(dotted: str, index: dict[str, str]) -> str | None:
        return index.get(dotted)

    def _resolve_js(self, source: str, spec: str, paths: set[str]) -> str | None:
        if spec.startswith("."):
            base = posixpath.normpath(posixpath.join(posixpath.dirname(source), spec))
        elif spec.startswith(("@/", "~/")):
            base = "src/" + spec[2:]
        else:
            return None
        if base in paths:
            return base
        for ext in JS_EXTS:
            if base + ext in paths:
                return base + ext
        for ext in JS_EXTS:
            if f"{base}/index{ext}" in paths:
                return f"{base}/index{ext}"
        return None

    def _java_class_index(self, files: list[FileInfo]) -> dict[str, str]:
        index: dict[str, str] = {}
        for f in files:
            if f.language in {"Java", "Kotlin"}:
                pkg = JAVA_PACKAGE.search(f.content)
                stem = posixpath.splitext(posixpath.basename(f.path))[0]
                if pkg:
                    index[f"{pkg.group(1)}.{stem}"] = f.path
        return index

    @staticmethod
    def _by_suffix(suffix: str, paths: set[str]) -> str | None:
        matches = [p for p in paths if p.endswith("/" + suffix) or p == suffix]
        return matches[0] if len(matches) == 1 else None

    def identify_modules(self, files: list[FileInfo]) -> list[ModuleInfo]:
        code_files = [f.path for f in files if is_code(f.language) or f.language in {"HTML", "CSS", "SCSS"}]
        groups = self._group_paths(code_files or [f.path for f in files], prefix="", depth=0)
        modules = [
            ModuleInfo(name=name or "(root)", path=name or ".", files=sorted(members))
            for name, members in groups.items()
        ]
        modules.sort(key=lambda m: (m.path.split("/")[0].lower() in AUX_DIRS, -len(m.files)))
        return modules

    def _group_paths(self, paths: list[str], prefix: str, depth: int) -> dict[str, list[str]]:
        buckets: dict[str, list[str]] = defaultdict(list)
        for path in paths:
            rest = path[len(prefix):]
            head = rest.split("/", 1)[0] if "/" in rest else ""
            buckets[prefix + head if head else prefix.rstrip("/")].append(path)

        result: dict[str, list[str]] = {}
        total = len(paths)
        for key, members in buckets.items():
            if not key or not any(p.startswith(key + "/") for p in members):
                result[key] = members
                continue
            remainders = [p[len(key) + 1:] for p in members]
            subdirs = {r.split("/", 1)[0] for r in remainders if "/" in r}
            has_direct_files = any("/" not in r for r in remainders)
            single_chain = len(subdirs) == 1 and not has_direct_files and depth < 6
            dominant = len(members) > max(12, 0.45 * total) and len(subdirs) >= 2 and depth < 3
            if single_chain or dominant:
                result.update(self._group_paths(members, key + "/", depth + 1))
            else:
                result[key] = members
        return result

    def analyze_file_complexity(self, files: list[FileInfo]) -> list[FileMetrics]:
        metrics: list[FileMetrics] = []
        for f in files:
            lines = [line.strip() for line in f.content.splitlines()]
            loc = sum(1 for line in lines if line and not line.startswith(COMMENT_PREFIXES))
            func_re = FUNC_PATTERNS.get(f.language)
            imports = sum(1 for line in lines if line.startswith(("import ", "from ", "#include", "require(", "use ")) or "require(" in line)
            metrics.append(
                FileMetrics(
                    path=f.path,
                    language=f.language,
                    lines_of_code=loc,
                    num_functions=len(func_re.findall(f.content)) if func_re else 0,
                    num_classes=len(CLASS_PATTERN.findall(f.content)) if is_code(f.language) else 0,
                    num_imports=imports if is_code(f.language) else 0,
                    is_test=is_test_file(f.path),
                )
            )
        metrics.sort(key=lambda m: -m.lines_of_code)
        return metrics

    def extract_api_endpoints(self, files: list[FileInfo]) -> list[ApiEndpoint]:
        endpoints: list[ApiEndpoint] = []
        seen: set[tuple[str, str, str]] = set()

        def add(path: str, method: str, route: str, framework: str, pos: int, content: str) -> None:
            key = (path, method, route)
            if key in seen:
                return
            seen.add(key)
            endpoints.append(ApiEndpoint(file_path=path, method=method, route=route or "/", framework=framework, line=content.count("\n", 0, pos) + 1))

        for f in files:
            if not is_code(f.language) or is_test_file(f.path):
                continue
            content = f.content
            for framework, pattern in ENDPOINT_PATTERNS:
                if framework in {"FastAPI/Flask", "Flask", "Django"} and f.language != "Python":
                    continue
                if framework == "Express" and f.language not in {"JavaScript", "TypeScript"}:
                    continue
                if framework == "Spring" and f.language not in {"Java", "Kotlin"}:
                    continue
                if framework == "NestJS" and f.language != "TypeScript":
                    continue
                for match in pattern.finditer(content):
                    if framework == "FastAPI/Flask":
                        label = "FastAPI" if "fastapi" in content.lower() else "Flask" if "flask" in content.lower() else "Python"
                        add(f.path, match.group(1).upper(), match.group(2), label, match.start(), content)
                    elif framework == "Flask":
                        methods = re.findall(r"['\"](\w+)['\"]", match.group(2) or "") or ["GET"]
                        for method in methods:
                            add(f.path, method.upper(), match.group(1), "Flask", match.start(), content)
                    elif framework == "Django":
                        if "urlpatterns" in content:
                            add(f.path, "ANY", "/" + match.group(1).lstrip("^/"), "Django", match.start(), content)
                    elif framework == "Spring":
                        verb = match.group(1).upper()
                        add(f.path, "ANY" if verb == "REQUEST" else verb, match.group(2), "Spring", match.start(), content)
                    else:
                        add(f.path, match.group(1).upper(), match.group(2), framework, match.start(), content)

            name = f.path.rsplit("/", 1)[-1]
            if f.language in {"JavaScript", "TypeScript"}:
                if re.search(r"(^|/)app/(.+/)?route\.[jt]s$", f.path):
                    route = "/" + re.sub(r"(^|.*/)app/|/?route\.[jt]s$", "", f.path)
                    for verb in re.findall(r"export\s+(?:async\s+)?function\s+(GET|POST|PUT|PATCH|DELETE)\b", content):
                        add(f.path, verb, route, "Next.js", 0, content)
                elif re.search(r"(^|/)pages/api/", f.path) and not name.startswith("_"):
                    route = "/api/" + re.sub(r"^.*pages/api/|\.[jt]sx?$", "", f.path).removesuffix("/index")
                    add(f.path, "ANY", route, "Next.js", 0, content)
        return endpoints[:300]

    def detect_patterns(self, files: list[FileInfo], paths: list[str]) -> dict[str, Any]:
        blob = "\n".join(f.content[:4000] for f in files if is_code(f.language)).lower()
        joined_paths = "\n".join(paths).lower()

        def detect(options: dict[str, list[str]]) -> list[str]:
            return [label for label, needles in options.items() if any(n in blob for n in needles)]

        patterns: dict[str, Any] = {
            "testing": detect({
                "pytest": ["import pytest", "@pytest."], "unittest": ["import unittest"], "Jest": ["from '@jest", "jest.fn(", "jest.mock("],
                "Vitest": ["from 'vitest'", 'from "vitest"'], "Mocha/Chai": ["from 'chai'", "require('chai')"], "JUnit": ["org.junit"],
                "Playwright": ["@playwright/test"], "Cypress": ["cy.visit("], "RSpec": ["rspec.describe"],
            }) + (["Go testing"] if any(p.endswith("_test.go") for p in paths) else []),
            "database": detect({
                "SQLAlchemy": ["sqlalchemy"], "Django ORM": ["from django.db import models"], "Prisma": ["@prisma/client"],
                "TypeORM": ["from 'typeorm'", 'from "typeorm"'], "Mongoose/MongoDB": ["mongoose", "pymongo", "mongodb"],
                "Sequelize": ["sequelize"], "JPA/Hibernate": ["javax.persistence", "jakarta.persistence", "hibernate"], "GORM": ["gorm.io"],
                "Redis": ["redis"], "SQLite": ["sqlite"], "PostgreSQL": ["psycopg", "postgres"],
            }),
            "auth": detect({
                "JWT": ["jwt", "jsonwebtoken"], "OAuth": ["oauth"], "Sessions/Cookies": ["session[", "express-session", "flask_login", "set_cookie"],
                "Passport": ["passport"], "NextAuth": ["next-auth"], "Spring Security": ["springframework.security"],
            }),
            "state_management": detect({
                "Redux": ["@reduxjs/toolkit", "from 'redux'", "createslice"], "Zustand": ["zustand"], "Vuex/Pinia": ["vuex", "pinia"],
                "React Context": ["createcontext("], "MobX": ["mobx"], "React Query": ["@tanstack/react-query", "react-query"],
            }),
            "ci_cd": [label for label, needle in {
                "GitHub Actions": ".github/workflows/", "GitLab CI": ".gitlab-ci.yml", "CircleCI": ".circleci/", "Jenkins": "jenkinsfile",
                "Docker": "dockerfile", "Kubernetes": "k8s/",
            }.items() if needle in joined_paths],
        }

        top_dirs = {p.split("/")[0] for p in paths if "/" in p}
        all_dirs = {part for p in paths for part in p.split("/")[:-1]}
        if {"models", "views", "controllers"} <= all_dirs or {"models", "views", "templates"} <= all_dirs:
            architecture = "MVC / layered"
        elif {"services", "packages"} & top_dirs and sum(1 for p in paths if p.endswith(("Dockerfile", "package.json", "go.mod"))) > 3:
            architecture = "Monorepo / multi-service"
        elif {"domain", "application", "infrastructure"} <= all_dirs:
            architecture = "Clean / hexagonal architecture"
        elif {"components", "pages"} & all_dirs or {"components", "app"} <= all_dirs:
            architecture = "Component-based frontend"
        elif {"routes", "services"} <= all_dirs or {"api", "services"} <= all_dirs:
            architecture = "Layered API (routes → services)"
        else:
            architecture = "Library / single package"
        patterns["architecture"] = architecture
        return {k: v for k, v in patterns.items() if v}

    def compute_hotspots(self, dependencies: list[DependencyEdge], limit: int = 12) -> list[dict[str, Any]]:
        incoming = Counter(e.target for e in dependencies)
        outgoing = Counter(e.source for e in dependencies)
        return [
            {"path": path, "imported_by": count, "imports": outgoing.get(path, 0)}
            for path, count in incoming.most_common(limit)
        ]

    def get_key_files(
        self,
        files: list[FileInfo],
        entry_points: list[str],
        hotspots: list[dict[str, Any]],
        endpoints: list[ApiEndpoint],
        limit: int = 15,
    ) -> list[str]:
        scores: Counter[str] = Counter()
        for i, path in enumerate(entry_points):
            scores[path] += 10 - min(i, 5)
        for i, spot in enumerate(hotspots):
            scores[spot["path"]] += 8 - min(i, 6)
        for endpoint in endpoints:
            scores[endpoint.file_path] += 2
        for f in files:
            name = f.path.rsplit("/", 1)[-1].lower()
            depth = f.path.count("/")
            if depth == 0 and name.startswith("readme"):
                scores[f.path] += 12
            if depth <= 1 and name in {"package.json", "pyproject.toml", "requirements.txt", "go.mod", "pom.xml", "cargo.toml", "dockerfile", "docker-compose.yml"}:
                scores[f.path] += 6
            if name in {"config.py", "settings.py", "config.ts", "config.js", "routes.py", "urls.py", "models.py", "schema.prisma", "router.ts", "routes.ts"}:
                scores[f.path] += 5
            if name.startswith("contributing"):
                scores[f.path] += 4
            if is_test_file(f.path):
                scores[f.path] -= 5
        return [path for path, score in scores.most_common(limit) if score > 0]

    @staticmethod
    def find_tests_for(path: str, test_paths: list[str], limit: int = 3) -> list[str]:
        stem = posixpath.splitext(posixpath.basename(path))[0].lower()
        if stem in {"index", "__init__", "main", "app", "utils"} or len(stem) < 3:
            return []
        return [t for t in test_paths if stem in posixpath.basename(t).lower()][:limit]
