import posixpath
from typing import Any

from models.schemas import MappedFile, TicketMapResponse
from services.code_analyzer import CodeAnalyzer
from services.llm_client import GeminiClient, LLMError
from services.store import Workspace
from utils.file_helpers import is_code, is_test_file, truncate

SYSTEM_PROMPT = (
    "You are a tech lead triaging a ticket for a developer who is new to this repository. Map the ticket to the concrete "
    "files, tests and APIs involved. You may ONLY reference existing files that appear in the ALL FILES list; new files are "
    "allowed only with change_type \"create\" and must sit in an existing folder that follows the project's layout."
)


class TicketMapper:
    def __init__(self, llm: GeminiClient) -> None:
        self.llm = llm

    async def map_ticket(self, ws: Workspace, ticket: str) -> TicketMapResponse:
        hits = ws.retriever.search(ticket, limit=12)
        if not self.llm.configured:
            return self._offline(ws, hits, "No Gemini API key is configured - showing keyword matches only.")

        analysis = ws.analysis
        excerpts = "\n\n".join(f"--- {f.path} ---\n{truncate(f.content, 3500)}" for f, _ in hits)
        endpoints = "\n".join(f"- {e.method} {e.route} ({e.file_path}:{e.line})" for e in analysis.api_endpoints[:60])
        modules = "\n".join(f"- `{m.path}`: {m.description}" for m in analysis.modules[:25])

        prompt = f"""REPOSITORY: {analysis.repo_name}
TECH STACK: {', '.join(analysis.tech_stack)}
PATTERNS: {analysis.patterns}

ARCHITECTURE (excerpt):
{truncate(analysis.architecture_summary, 2500)}

MODULES:
{modules}

API ENDPOINTS:
{endpoints or '- none detected'}

ALL FILES:
{ws.file_index()}

MOST RELEVANT FILE EXCERPTS (keyword search):
{excerpts or '(none)'}

TICKET:
{ticket}

Respond with JSON only, using this exact shape:
{{
  "summary": "one or two sentences restating what the ticket requires in terms of this codebase",
  "relevant_files": [
    {{"path": "exact/path", "reason": "what must change here and why", "relevance_score": 0.0-1.0, "change_type": "modify|create|review"}}
  ],
  "suggested_tests": ["existing test file to update, or new test file path to create"],
  "related_apis": ["METHOD /route"],
  "implementation_steps": ["Step-by-step, each naming the file(s) involved"],
  "risks": ["things that could break or need care"],
  "estimated_effort": "e.g. ~0.5 day / 1-2 days, with a short justification"
}}
Include 3-10 relevant files sorted by relevance_score descending."""
        try:
            data = await self.llm.generate_json(prompt, system=SYSTEM_PROMPT, temperature=0.2, deadline_seconds=120)
        except LLMError:
            return self._offline(ws, hits, "The AI model is temporarily unavailable - showing keyword matches only.")
        if not isinstance(data, dict):
            return self._offline(ws, hits, "The AI response could not be parsed - showing keyword matches only.")
        return self._post_process(ws, data)

    def _post_process(self, ws: Workspace, data: dict[str, Any]) -> TicketMapResponse:
        existing_dirs = {posixpath.dirname(p) for p in ws.by_path}
        by_basename: dict[str, list[str]] = {}
        for p in ws.by_path:
            by_basename.setdefault(posixpath.basename(p), []).append(p)

        mapped: list[MappedFile] = []
        seen: set[str] = set()
        for item in data.get("relevant_files") or []:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path", "")).strip().removeprefix("./").lstrip("/")
            change = item.get("change_type") if item.get("change_type") in {"modify", "create", "review"} else "modify"
            exists = path in ws.by_path
            if not exists and change != "create":
                candidates = by_basename.get(posixpath.basename(path), [])
                if len(candidates) == 1:
                    path, exists = candidates[0], True
                else:
                    continue
            if not exists and posixpath.dirname(path) not in existing_dirs:
                continue
            if path in seen:
                continue
            seen.add(path)
            try:
                score = max(0.0, min(1.0, float(item.get("relevance_score", 0.5))))
            except (TypeError, ValueError):
                score = 0.5
            mapped.append(MappedFile(path=path, reason=str(item.get("reason", "")), relevance_score=score, change_type=change, exists=exists))
        mapped.sort(key=lambda m: -m.relevance_score)

        test_paths = [p for p, f in ws.by_path.items() if is_test_file(p) and is_code(f.language)]
        tests = [str(t).strip() for t in data.get("suggested_tests") or [] if isinstance(t, str)]
        for m in mapped[:5]:
            for t in CodeAnalyzer.find_tests_for(m.path, test_paths):
                if t not in tests:
                    tests.append(t)

        apis = [str(a) for a in data.get("related_apis") or [] if isinstance(a, str)]
        mapped_paths = {m.path for m in mapped}
        for e in ws.analysis.api_endpoints:
            label = f"{e.method} {e.route}"
            already = any(a.split(" (")[0].strip() == label for a in apis)
            if e.file_path in mapped_paths and not already and len(apis) < 12:
                apis.append(label)

        return TicketMapResponse(
            summary=str(data.get("summary", "")),
            relevant_files=mapped[:10],
            suggested_tests=tests[:8],
            related_apis=apis,
            implementation_steps=[str(s) for s in data.get("implementation_steps") or []][:12],
            risks=[str(r) for r in data.get("risks") or []][:6],
            estimated_effort=str(data.get("estimated_effort", "")),
        )

    @staticmethod
    def _offline(ws: Workspace, hits: list, note: str) -> TicketMapResponse:
        top = hits[0][1] if hits else 1.0
        files = [
            MappedFile(path=f.path, reason="Keyword match with the ticket text", relevance_score=round(score / top, 2))
            for f, score in hits[:8]
        ]
        return TicketMapResponse(summary=note, relevant_files=files)
