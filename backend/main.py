"""
AI Job Agent - FastAPI Main Server
Web API serving the dashboard and all backend functionality.
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.config import settings
from backend.database import (
    init_db,
    get_all_jobs,
    get_job,
    insert_job,
    update_job,
    get_applications,
    insert_application,
    get_all_settings,
    get_setting,
    set_setting,
    get_stats,
    log_search,
)
from backend.search.serpapi_client import serpapi_client
from backend.search.job_parser import job_parser
from backend.resume.latex_parser import LaTeXResumeParser
from backend.resume.analyzer import resume_analyzer
from backend.apply.engine import auto_apply_engine

# ========================
# App Setup
# ========================

app = FastAPI(
    title="AI Job Agent",
    description="AI-powered job search, resume tailoring, and auto-apply automation",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend static files
FRONTEND_DIR = settings.BASE_DIR / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.on_event("startup")
async def startup():
    """Initialize database on startup."""
    await init_db()
    settings.ensure_dirs()


# ========================
# Pydantic Models
# ========================

class SearchRequest(BaseModel):
    job_title: str
    location: str = ""
    job_type: str = ""  # e.g., 'Remote', 'Internship', 'Hybrid'
    num_results: int = 20
    date_filter: str = ""  # 'd', 'w', 'm', 'y'
    platforms: Optional[List[str]] = None
    exclude_terms: Optional[List[str]] = None
    enrich: bool = True  # Whether to fetch full job descriptions


class AnalyzeRequest(BaseModel):
    job_id: int
    resume_path: Optional[str] = None


class TailorRequest(BaseModel):
    job_id: int
    resume_path: Optional[str] = None


class AutoApplyRequest(BaseModel):
    job_ids: List[int]
    max_applications: int = 5
    resume_path: Optional[str] = None


class SettingsUpdate(BaseModel):
    applicant_name: Optional[str] = None
    applicant_email: Optional[str] = None
    applicant_phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    max_applications: Optional[int] = None


# ========================
# Routes - Dashboard
# ========================

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serve the main dashboard."""
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>AI Job Agent</h1><p>Frontend not found. Place index.html in /frontend/</p>")


# ========================
# Routes - Job Search
# ========================

@app.post("/api/search")
async def search_jobs(request: SearchRequest):
    """Search for jobs across ATS platforms."""
    if not settings.SERPAPI_KEY:
        raise HTTPException(status_code=400, detail="SerpAPI key not configured. Set SERPAPI_KEY in .env")

    # Search via SerpAPI
    results = await serpapi_client.search(
        job_title=request.job_title,
        location=request.location,
        job_type=request.job_type,
        num_results=request.num_results,
        date_filter=request.date_filter,
        platforms=request.platforms,
        exclude_terms=request.exclude_terms,
    )

    # Google Jobs API already provides full descriptions — enrichment not needed.
    # But we still attempt to enrich any jobs that have very short descriptions.
    if request.enrich and results:
        short_desc_jobs = [j for j in results if len(j.get("description", "")) < 200]
        if short_desc_jobs:
            await job_parser.enrich_jobs(short_desc_jobs)

    # Save to database
    saved_jobs = []
    for job in results:
        job_id = await insert_job(job)
        if job_id:
            job["id"] = job_id
            saved_jobs.append(job)

    # Log the search
    await log_search(request.job_title, request.location, len(saved_jobs))

    return {
        "query": request.job_title,
        "location": request.location,
        "total_results": len(saved_jobs),
        "jobs": saved_jobs,
    }


@app.get("/api/jobs")
async def list_jobs(status: Optional[str] = None, limit: int = 50):
    """Get all saved jobs."""
    jobs = await get_all_jobs(status=status, limit=limit)
    return {"jobs": jobs, "total": len(jobs)}


@app.get("/api/jobs/{job_id}")
async def get_job_detail(job_id: int):
    """Get a single job's details."""
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# ========================
# Routes - Resume
# ========================

@app.post("/api/resume/upload")
async def upload_resume(file: UploadFile = File(...)):
    """Upload a resume file (.tex, .txt, .pdf)."""
    if not file.filename.lower().endswith((".tex", ".txt", ".pdf")):
        raise HTTPException(status_code=400, detail="Only .tex, .txt, and .pdf files are supported")

    # Save the file
    upload_path = settings.RESUMES_DIR / f"base_resume{Path(file.filename).suffix.lower()}"
    content = await file.read()
    upload_path.write_bytes(content)

    # Store the path in settings
    await set_setting("base_resume_path", str(upload_path))

    # Parse and validate
    try:
        if upload_path.suffix == ".pdf":
            from backend.resume.pdf_parser import PDFResumeParser
            parser = PDFResumeParser()
            data = parser.parse(str(upload_path))
            text = parser.get_text_content()
        elif upload_path.suffix == ".txt":
            text = upload_path.read_text(encoding="utf-8")
            data = {"sections": {"content": text}}
        else:
            parser = LaTeXResumeParser()
            data = parser.parse(str(upload_path))
            text = parser.get_text_content()
            
        return {
            "message": "Resume uploaded successfully",
            "path": str(upload_path),
            "sections": list(data["sections"].keys()),
            "preview": text[:500],
        }
    except Exception as e:
        return {
            "message": "Resume uploaded but parsing failed",
            "path": str(upload_path),
            "error": str(e),
        }


@app.post("/api/resume/analyze")
async def analyze_resume(request: AnalyzeRequest):
    """Analyze resume against a job description."""
    if not settings.GEMINI_API_KEY:
        raise HTTPException(status_code=400, detail="Gemini API key not configured. Set GEMINI_API_KEY in .env")

    job = await get_job(request.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Get resume path
    resume_path = request.resume_path or await get_setting("base_resume_path")
    if not resume_path:
        # Fall back to template
        resume_path = str(settings.TEMPLATES_DIR / "resume_template.tex")

    # Parse resume
    try:
        suffix = Path(resume_path).suffix.lower()
        if suffix == ".pdf":
            from backend.resume.pdf_parser import PDFResumeParser
            parser = PDFResumeParser()
            parser.parse(resume_path)
            resume_text = parser.get_text_content()
        elif suffix == ".txt":
            resume_text = Path(resume_path).read_text(encoding="utf-8")
        else:
            parser = LaTeXResumeParser()
            parser.parse(resume_path)
            resume_text = parser.get_text_content()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse resume: {e}")

    # Analyze
    analysis = await resume_analyzer.analyze(resume_text, job["description"])

    # Update job with match score
    await update_job(request.job_id, {
        "match_score": analysis.get("match_score", 0),
        "keywords_missing": json.dumps(analysis.get("missing_keywords", [])),
        "status": "analyzed",
    })

    return {
        "job_id": request.job_id,
        "job_title": job["title"],
        "company": job["company"],
        "analysis": analysis,
    }


@app.post("/api/resume/tailor")
async def tailor_resume(request: TailorRequest):
    """Tailor resume for a specific job."""
    if not settings.GEMINI_API_KEY:
        raise HTTPException(status_code=400, detail="Gemini API key not configured")

    job = await get_job(request.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    resume_path = request.resume_path or await get_setting("base_resume_path")
    if not resume_path:
        resume_path = str(settings.TEMPLATES_DIR / "resume_template.tex")

    # First analyze
    suffix = Path(resume_path).suffix.lower()
    if suffix == ".pdf":
        from backend.resume.pdf_parser import PDFResumeParser
        parser = PDFResumeParser()
        parser.parse(resume_path)
        resume_text = parser.get_text_content()
    elif suffix == ".txt":
        resume_text = Path(resume_path).read_text(encoding="utf-8")
    else:
        parser = LaTeXResumeParser()
        parser.parse(resume_path)
        resume_text = parser.get_text_content()
        
    analysis = await resume_analyzer.analyze(resume_text, job["description"])

    # Then tailor
    result = await resume_tailor.tailor(
        resume_path,
        job["description"],
        analysis,
        job["title"],
        job["company"],
    )

    return {
        "job_id": request.job_id,
        "job_title": job["title"],
        "company": job["company"],
        "match_score": analysis.get("match_score", 0),
        "tailor_result": result,
    }


# ========================
# Routes - Auto-Apply
# ========================

@app.post("/api/apply")
async def auto_apply(request: AutoApplyRequest):
    """Start auto-apply process for selected jobs."""
    resume_path = request.resume_path or await get_setting("base_resume_path")
    if not resume_path:
        resume_path = str(settings.TEMPLATES_DIR / "resume_template.tex")

    # Get job details
    jobs = []
    for job_id in request.job_ids:
        job = await get_job(job_id)
        if job:
            jobs.append(job)

    if not jobs:
        raise HTTPException(status_code=400, detail="No valid jobs found")

    # Start auto-apply in background
    asyncio.create_task(
        auto_apply_engine.run(jobs, resume_path, request.max_applications)
    )

    return {
        "message": "Auto-apply started",
        "total_jobs": len(jobs),
        "max_applications": request.max_applications,
    }


@app.get("/api/apply/progress")
async def get_apply_progress():
    """Get auto-apply progress."""
    return auto_apply_engine.get_progress()


@app.post("/api/apply/stop")
async def stop_apply():
    """Stop the auto-apply process."""
    auto_apply_engine.stop()
    return {"message": "Auto-apply stopped"}


# ========================
# Routes - History & Stats
# ========================

@app.get("/api/history")
async def get_history(limit: int = 50):
    """Get application history."""
    applications = await get_applications(limit=limit)
    return {"applications": applications, "total": len(applications)}


@app.get("/api/stats")
async def get_dashboard_stats():
    """Get dashboard statistics."""
    stats = await get_stats()
    return stats


# ========================
# Routes - Settings
# ========================

@app.get("/api/settings")
async def get_settings():
    """Get all settings."""
    all_settings = await get_all_settings()
    return all_settings


@app.post("/api/settings")
async def update_settings(request: SettingsUpdate):
    """Update settings."""
    if request.applicant_name is not None:
        await set_setting("applicant_name", request.applicant_name)
    if request.applicant_email is not None:
        await set_setting("applicant_email", request.applicant_email)
    if request.applicant_phone is not None:
        await set_setting("applicant_phone", request.applicant_phone)
    if request.linkedin_url is not None:
        await set_setting("linkedin_url", request.linkedin_url)
    if request.max_applications is not None:
        await set_setting("max_applications", str(request.max_applications))
    return {"message": "Settings updated"}


# ========================
# Health Check
# ========================

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "serpapi_configured": bool(settings.SERPAPI_KEY),
        "gemini_configured": bool(settings.GEMINI_API_KEY),
        "timestamp": datetime.now().isoformat(),
    }


# ========================
# Run
# ========================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
    )
