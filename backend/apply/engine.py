"""
AI Job Agent - Auto-Apply Engine
Orchestrates the automated job application process.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from backend.config import settings
from backend.database import (
    insert_application,
    update_application,
    update_job,
    get_setting,
    set_setting,
)
from backend.resume.analyzer import resume_analyzer
from backend.resume.tailor import resume_tailor
from backend.resume.latex_parser import LaTeXResumeParser
from backend.resume.cover_letter import cover_letter_generator


class AutoApplyEngine:
    """
    Orchestrates the full auto-apply pipeline:
    Search → Analyze → Tailor → Apply → Log
    """

    def __init__(self):
        self.is_running = False
        self.current_progress = {
            "total": 0,
            "completed": 0,
            "current_job": "",
            "status": "idle",
            "results": [],
        }

    async def run(
        self,
        jobs: list,
        resume_path: str,
        max_applications: int = 5,
    ) -> dict:
        """
        Run the auto-apply pipeline on a list of jobs.

        Args:
            jobs: List of job dicts with 'id', 'title', 'company', 'description', 'url', 'ats_platform'
            resume_path: Path to the base resume .tex file
            max_applications: Maximum number of applications to submit

        Returns:
            Summary dict with results
        """
        if self.is_running:
            return {"error": "Auto-apply is already running"}

        self.is_running = True
        self.current_progress = {
            "total": min(len(jobs), max_applications),
            "completed": 0,
            "current_job": "",
            "status": "running",
            "results": [],
        }

        results = []

        try:
            import traceback
            # Parse the base resume
            resume_ext = Path(resume_path).suffix.lower()
            if resume_ext == ".pdf":
                from backend.resume.pdf_parser import PDFResumeParser
                parser = PDFResumeParser()
                parser.parse(resume_path)
                resume_text = parser.get_text_content()
                resume_data = {"sections": {"content": resume_text}}
            elif resume_ext == ".txt":
                resume_text = Path(resume_path).read_text(encoding="utf-8")
                resume_data = {"sections": {"content": resume_text}}
            else:
                parser = LaTeXResumeParser()
                resume_data = parser.parse(resume_path)
                resume_text = parser.get_text_content()
        except Exception as e:
            self.is_running = False
            self.current_progress["status"] = f"Failed to read resume: {str(e)}"
            import traceback
            traceback.print_exc()
            return {"error": f"Resume parse error: {str(e)}"}

        try:
            jobs_to_process = jobs[:max_applications]

            for i, job in enumerate(jobs_to_process):
                if not self.is_running:
                    break

                self.current_progress["current_job"] = f"{job.get('title', '')} at {job.get('company', '')}"
                self.current_progress["status"] = f"Processing {i+1}/{len(jobs_to_process)}"

                result = await self._process_single_job(
                    job, resume_path, resume_text, resume_data
                )
                results.append(result)
                self.current_progress["completed"] = i + 1
                self.current_progress["results"].append(result)

                # Delay between applications
                if i < len(jobs_to_process) - 1:
                    await asyncio.sleep(settings.APPLY_DELAY_SECONDS)

        except Exception as e:
            self.current_progress["status"] = f"Error: {str(e)}"
            import traceback
            traceback.print_exc()
        finally:
            self.is_running = False
            self.current_progress["status"] = "completed"

        return {
            "total_processed": len(results),
            "successful": sum(1 for r in results if r.get("status") == "applied"),
            "failed": sum(1 for r in results if r.get("status") == "failed"),
            "results": results,
        }

    async def _process_single_job(
        self, job: dict, resume_path: str, resume_text: str, resume_data: dict
    ) -> dict:
        """Process a single job: analyze → tailor → record."""
        job_id = job.get("id")
        result = {
            "job_id": job_id,
            "job_title": job.get("title", ""),
            "company": job.get("company", ""),
            "status": "pending",
            "match_score": 0,
            "tailored_resume": None,
            "error": None,
        }

        try:
            # Step 1: Analyze, Tailor, and Generate Cover Letter in ONE call
            from backend.resume.unified_processor import unified_processor
            
            applicant_name = await get_setting("applicant_name") or "Applicant"
            
            # Ensure we have a job description
            desc = job.get("description", "")
            if not desc or len(desc) < 100:
                from backend.search.job_parser import job_parser
                desc = await job_parser.fetch_job_description(job.get("url", ""), job.get("ats_platform", "default"))
                if desc:
                    job["description"] = desc

            # Unified Processing
            print(f"[Engine] Starting unified AI processing for {job.get('title')} at {job.get('company')}...")
            ai_data = await unified_processor.process_job(
                resume_text,
                resume_path,
                job.get("description", ""),
                job.get("title", ""),
                job.get("company", ""),
                applicant_name
            )

            if ai_data.get("error"):
                result["status"] = "failed"
                result["error"] = f"AI processing failed: {ai_data['error']}"
                return result

            # Map unified results back to result dict
            match_score = ai_data.get("match_score", 0)
            result["match_score"] = match_score
            result["cover_letter"] = ai_data.get("cover_letter", "")
            
            # Step 2: Handle LaTeX Tailoring (if applicable and requested)
            suffix = Path(resume_path).suffix.lower()
            if suffix == ".tex" and match_score < 95:
                # We still use the existing tailor logic to actually edit the LaTeX file
                # but we pass the already generated analysis to save a call
                tailor_result = await resume_tailor.tailor(
                    resume_path,
                    job.get("description", ""),
                    ai_data, # Use unified AI data as analysis
                    job.get("title", ""),
                    job.get("company", ""),
                )
                if tailor_result.get("output_path"):
                    result["tailored_resume"] = tailor_result["output_path"]
                    result["changes_made"] = tailor_result.get("changes_made", [])
            else:
                # For non-LaTeX or good match, use original resume
                result["tailored_resume"] = resume_path
                result["changes_made"] = []

            # Update job record in database
            if job_id:
                await update_job(job_id, {
                    "match_score": match_score,
                    "status": "analyzed",
                    "keywords_missing": json.dumps(ai_data.get("missing_keywords", []))
                })

            # Step 3: Check match score threshold
            if match_score < 40:
                result["status"] = "failed"
                result["error"] = f"Match score too low ({match_score}%)"
                return result

            # Step 4: Record the application (auto-apply via browser is complex)
            app_data = {
                "job_id": job_id,
                "resume_path": resume_path,
                "tailored_resume_path": result.get("tailored_resume", ""),
                "status": "ready",
                "notes": f"Match score: {match_score}%. Tailored resume generated.",
            }
            app_id = await insert_application(app_data)

            # Step 4: Attempt auto-apply via browser
            apply_success = await self._attempt_apply(
                job, result.get("tailored_resume") or resume_path, result.get("cover_letter", "")
            )

            if apply_success:
                result["status"] = "applied"
                if job_id:
                    await update_job(job_id, {"status": "applied"})
                await update_application(app_id, {
                    "status": "applied",
                    "applied_at": datetime.now().isoformat(),
                })
            else:
                result["status"] = "ready"
                result["note"] = "Auto-apply prepared. Manual submission may be needed."

        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"[Engine Error] Job {job_id}: {error_trace}")
            result["status"] = "failed"
            result["error"] = str(e)
            if "match_score" not in result or result["match_score"] == 0:
                result["match_score"] = 0

        return result

    async def _attempt_apply(self, job: dict, resume_path: str, cover_letter: str = "") -> bool:
        """
        Attempt to auto-apply to a job using browser automation.
        Currently supports Greenhouse and Lever.

        Returns True if application was submitted successfully.
        """
        platform = job.get("ats_platform", "").lower()

        try:
            if platform == "greenhouse":
                from backend.apply.greenhouse import apply_greenhouse
                return await apply_greenhouse(job, resume_path, cover_letter)
            elif platform == "lever":
                from backend.apply.lever import apply_lever
                return await apply_lever(job, resume_path, cover_letter)
            else:
                # For unsupported platforms, mark as ready for manual apply
                return False
        except Exception as e:
            print(f"[AutoApply Error] {platform}: {e}")
            return False

    def stop(self):
        """Stop the auto-apply process."""
        self.is_running = False
        self.current_progress["status"] = "stopped"

    def get_progress(self) -> dict:
        """Get current progress."""
        return self.current_progress


# Singleton
auto_apply_engine = AutoApplyEngine()
