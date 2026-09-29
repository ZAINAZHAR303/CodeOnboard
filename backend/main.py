import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config import settings
from models.schemas import (
    AnalysisResult,
    AnalysisSummary,
    AnalyzeRequest,
    ChatRequest,
    ChatResponse,
    JobStatus,
    TicketMapRequest,
    TicketMapResponse,
)
from services.code_analyzer import CodeAnalyzer
from services.doc_generator import DocGenerator
from services.llm_client import GeminiClient
from services.pipeline import JobManager
from services.qa_agent import QAAgent
from services.repo_ingester import IngestError, RepoIngester, parse_github_url
from services.store import AnalysisStore, Workspace
from services.ticket_mapper import TicketMapper

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("codeonboard")

llm = GeminiClient()
store = AnalysisStore()
jobs = JobManager(store, RepoIngester(), CodeAnalyzer(), DocGenerator(llm))
qa_agent = QAAgent(llm)
ticket_mapper = TicketMapper(llm)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not settings.llm_configured:
        logger.warning("GEMINI_API_KEY is not set - AI sections will use static-analysis fallbacks")
    logger.info("CodeOnboard API ready (model=%s)", settings.gemini_model)
    yield
    await llm.close()


app = FastAPI(title="CodeOnboard API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_error(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def _workspace(repo_id: str) -> Workspace:
    try:
        return store.get(repo_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Analysis not found") from None


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "version": app.version, "llm_configured": settings.llm_configured, "model": settings.gemini_model}


@app.post("/api/analyze")
async def analyze(request: AnalyzeRequest) -> dict:
    try:
        ref = parse_github_url(request.repo_url, request.branch)
    except IngestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    if not request.force:
        existing = store.find_existing(ref.web_url, ref.branch)
        if existing:
            return {"cached": True, "repo_id": existing, "job_id": None}
    job = jobs.start(ref)
    return {"cached": False, "repo_id": None, "job_id": job.job_id}


@app.get("/api/jobs/{job_id}", response_model=JobStatus)
async def job_status(job_id: str) -> JobStatus:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/analyses", response_model=list[AnalysisSummary])
async def list_analyses() -> list[AnalysisSummary]:
    return store.list()


@app.get("/api/analysis/{repo_id}", response_model=AnalysisResult)
async def get_analysis(repo_id: str) -> AnalysisResult:
    return _workspace(repo_id).analysis


@app.get("/api/analysis/{repo_id}/file")
async def get_file(repo_id: str, path: str = Query(..., min_length=1)) -> dict:
    ws = _workspace(repo_id)
    f = ws.by_path.get(path)
    if not f:
        raise HTTPException(status_code=404, detail="File content not available (binary, too large, or not analysed)")
    imports = [e.target for e in ws.analysis.dependencies if e.source == path]
    imported_by = [e.source for e in ws.analysis.dependencies if e.target == path]
    return {"path": f.path, "language": f.language, "size": f.size, "content": f.content, "imports": imports, "imported_by": imported_by}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    return await qa_agent.ask(_workspace(request.repo_id), request.question.strip(), request.history)


@app.post("/api/map-ticket", response_model=TicketMapResponse)
async def map_ticket(request: TicketMapRequest) -> TicketMapResponse:
    return await ticket_mapper.map_ticket(_workspace(request.repo_id), request.ticket_description.strip())


if settings.frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=settings.frontend_dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        candidate = (settings.frontend_dist / full_path).resolve()
        if full_path and candidate.is_file() and settings.frontend_dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(settings.frontend_dist / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
