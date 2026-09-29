import posixpath

from models.schemas import ChatResponse, ChatTurn
from services.llm_client import GeminiClient, LLMError
from services.store import Workspace
from utils.file_helpers import truncate

SYSTEM_PROMPT = (
    "You are CodeOnboard, a senior engineer who knows this repository inside out and is mentoring a new team member. "
    "Answer ONLY from the repository context and source files provided. When you reference code, cite the file path in "
    "backticks (and the function/class name). If the context does not contain the answer, say what you could not find and "
    "point to the files most likely to contain it. Prefer short, well-structured markdown answers with concrete steps."
)


class QAAgent:
    def __init__(self, llm: GeminiClient) -> None:
        self.llm = llm

    def _retrieve(self, ws: Workspace, question: str, history: list[ChatTurn]) -> list[str]:
        mentioned = [p for p in ws.by_path if p in question or (len(posixpath.basename(p)) > 5 and posixpath.basename(p) in question)]
        recent_user = " ".join(t.content for t in history[-4:] if t.role == "user")
        hits = [f.path for f, _ in ws.retriever.search(f"{question} {question} {recent_user}", limit=8)]
        ordered: list[str] = []
        for path in [*mentioned, *hits]:
            if path not in ordered:
                ordered.append(path)
        return ordered[:8]

    async def ask(self, ws: Workspace, question: str, history: list[ChatTurn]) -> ChatResponse:
        paths = self._retrieve(ws, question, history)
        if not self.llm.configured:
            return self._offline_answer(paths)

        analysis = ws.analysis
        modules = "\n".join(f"- `{m.path}`: {m.description}" for m in analysis.modules[:25])
        endpoints = "\n".join(f"- {e.method} {e.route} ({e.file_path}:{e.line})" for e in analysis.api_endpoints[:40])
        sources = "\n\n".join(f"--- {p} ---\n{truncate(ws.by_path[p].content, 7000)}" for p in paths)
        convo = "\n".join(f"{t.role.upper()}: {truncate(t.content, 1500)}" for t in history[-6:])

        prompt = f"""REPOSITORY: {analysis.repo_name}
TECH STACK: {', '.join(analysis.tech_stack)}

ARCHITECTURE OVERVIEW:
{truncate(analysis.architecture_summary, 4000)}

MODULES:
{modules}

API ENDPOINTS:
{endpoints or '- none detected'}

ALL FILES:
{ws.file_index(max_lines=800)}

RETRIEVED SOURCE FILES:
{sources or '(no matching files)'}

CONVERSATION SO FAR:
{convo or '(none)'}

QUESTION: {question}

Respond with JSON only: {{"answer": "<markdown answer>", "relevant_files": ["<file paths from ALL FILES that matter most, max 6>"]}}"""
        try:
            data = await self.llm.generate_json(prompt, system=SYSTEM_PROMPT, temperature=0.2, deadline_seconds=90)
        except LLMError:
            return self._offline_answer(paths, failed=True)

        answer = str(data.get("answer") or "").strip() if isinstance(data, dict) else ""
        files = [p for p in (data.get("relevant_files") or []) if isinstance(p, str) and p in ws.by_path] if isinstance(data, dict) else []
        if not answer:
            return self._offline_answer(paths, failed=True)
        return ChatResponse(answer=answer, relevant_files=files[:6] or paths[:4])

    @staticmethod
    def _offline_answer(paths: list[str], failed: bool = False) -> ChatResponse:
        reason = "The AI model is temporarily unavailable." if failed else "No Gemini API key is configured."
        listing = "\n".join(f"- `{p}`" for p in paths[:6]) or "- (no matching files found)"
        return ChatResponse(answer=f"{reason} Based on a keyword search, these files are the best place to look:\n\n{listing}", relevant_files=paths[:6])
