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
            # Parse the base resume
            parser = LaTeXResumeParser()
            resume_data = parser.parse(resume_path)
            resume_text = parser.get_text_content()

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
            # Step 1: Analyze resume against job description
            analysis = await resume_analyzer.analyze(
                resume_text, job.get("description", "")
            )
            match_score = analysis.get("match_score", 0)
            result["match_score"] = match_score

            # Update job record with match score
            if job_id:
                await update_job(job_id, {
                    "match_score": match_score,
                    "keywords_missing": json.dumps(analysis.get("missing_keywords", [])),
                    "status": "analyzed",
                })

            # Step 2: Tailor resume if match score needs improvement
            if match_score < 95:  # Always tailor unless perfect match
                tailor_result = await resume_tailor.tailor(
                    resume_path,
                    job.get("description", ""),
                    analysis,
                    job.get("title", ""),
                    job.get("company", ""),
                )
                if tailor_result.get("output_path"):
                    result["tailored_resume"] = tailor_result["output_path"]
                    result["changes_made"] = tailor_result.get("changes_made", [])

            # Step 3: Record the application (auto-apply via browser is complex)
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
                job, result.get("tailored_resume") or resume_path
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
            result["status"] = "failed"
            result["error"] = str(e)

        return result

    async def _attempt_apply(self, job: dict, resume_path: str) -> bool:
        """
        Attempt to auto-apply to a job using browser automation.
        Currently supports Greenhouse and Lever.

        Returns True if application was submitted successfully.
        """
        platform = job.get("ats_platform", "").lower()

        try:
            if platform == "greenhouse":
                from backend.apply.greenhouse import apply_greenhouse
                return await apply_greenhouse(job, resume_path)
            elif platform == "lever":
                from backend.apply.lever import apply_lever
                return await apply_lever(job, resume_path)
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
