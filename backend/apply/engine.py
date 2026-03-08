"""
AI Job Agent - Auto-Apply Engine
Orchestrates the automated job application process.
One Gemini call per job via unified_processor (no duplicate calls).
"""

import asyncio
import json
import re
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
from backend.resume.latex_parser import LaTeXResumeParser
from backend.resume.unified_processor import unified_processor


class AutoApplyEngine:
    """
    Orchestrates the full auto-apply pipeline:
    Search → Analyze → Tailor (LaTeX) → Cover Letter → Apply → Log
    All AI work done in exactly ONE Gemini call per job.
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
            jobs: List of job dicts with 'id', 'title', 'company', 'description', 'url'
            resume_path: Path to the base resume file (.tex, .pdf, or .txt)
            max_applications: Cap on how many to process

        Returns:
            Summary dict with results
        """
        if self.is_running:
            return {"error": "Auto-apply is already running"}

        self.is_running = True
        jobs_to_process = jobs[:max_applications]
        self.current_progress = {
            "total": len(jobs_to_process),
            "completed": 0,
            "current_job": "",
            "status": "running",
            "results": [],
        }

        results = []

        # ── Parse base resume once ──────────────────────────────────────────
        try:
            resume_ext = Path(resume_path).suffix.lower()
            if resume_ext == ".pdf":
                from backend.resume.pdf_parser import PDFResumeParser
                parser = PDFResumeParser()
                parser.parse(resume_path)
                resume_text = parser.get_text_content()
            elif resume_ext == ".txt":
                resume_text = Path(resume_path).read_text(encoding="utf-8")
            else:
                # .tex (default / preferred)
                parser = LaTeXResumeParser()
                parser.parse(resume_path)
                resume_text = parser.get_text_content()
        except Exception as e:
            self.is_running = False
            self.current_progress["status"] = f"❌ Failed to read resume: {e}"
            import traceback; traceback.print_exc()
            return {"error": f"Resume parse error: {e}"}

        # ── Process each job ────────────────────────────────────────────────
        try:
            for i, job in enumerate(jobs_to_process):
                if not self.is_running:
                    break

                job_label = f"{job.get('title', '?')} @ {job.get('company', '?')}"
                self.current_progress["current_job"] = job_label
                self.current_progress["status"] = f"Processing {i+1}/{len(jobs_to_process)}: {job_label}"

                result = await self._process_single_job(job, resume_path, resume_text)
                results.append(result)
                self.current_progress["completed"] = i + 1
                self.current_progress["results"].append(result)

                # Delay between jobs to respect RPM limits
                if i < len(jobs_to_process) - 1:
                    wait = settings.APPLY_DELAY_SECONDS
                    print(f"[Engine] Waiting {wait}s before next job...")
                    await asyncio.sleep(wait)

        except Exception as e:
            import traceback
            self.current_progress["status"] = f"❌ Error: {e}"
            traceback.print_exc()
        finally:
            self.is_running = False
            self.current_progress["status"] = "completed"

        successful = sum(1 for r in results if r.get("status") in ("applied", "ready"))
        failed = sum(1 for r in results if r.get("status") == "failed")
        print(f"[Engine] Done. Successful: {successful}, Failed: {failed}")

        return {
            "total_processed": len(results),
            "successful": successful,
            "failed": failed,
            "results": results,
        }

    async def _process_single_job(
        self, job: dict, resume_path: str, resume_text: str
    ) -> dict:
        """
        Process a single job using exactly ONE Gemini call:
        analyze + LaTeX tailoring + cover letter → all at once.
        """
        job_id = job.get("id")
        result = {
            "job_id": job_id,
            "job_title": job.get("title", ""),
            "company": job.get("company", ""),
            "status": "pending",
            "match_score": 0,
            "tailored_resume": None,
            "cover_letter": "",
            "changes_made": [],
            "error": None,
        }

        try:
            # ── Ensure we have a real job description ──────────────────────
            desc = job.get("description", "")
            if not desc or len(desc) < 300:
                print(f"[Engine] Short/missing description for {job.get('title')} — trying to fetch from URL...")
                try:
                    from backend.search.job_parser import job_parser
                    fetched = await job_parser.fetch_job_description(
                        job.get("url", ""),
                        job.get("ats_platform", "default"),
                    )
                    if fetched and len(fetched) > 100:
                        desc = fetched
                        job["description"] = desc
                except Exception as fetch_err:
                    print(f"[Engine] Could not fetch JD: {fetch_err}")

            if not desc:
                result["status"] = "failed"
                result["error"] = "No job description available — cannot analyze."
                return result

            # ── Get applicant name from DB or .env ─────────────────────────
            applicant_name = (
                await get_setting("applicant_name")
                or settings.APPLICANT_NAME
                or "Applicant"
            )

            # ── ONE Gemini call: analyze + tailor + cover letter ───────────
            print(f"[Engine] 🤖 Calling Gemini for: {job.get('title')} @ {job.get('company')}")
            ai_data = await unified_processor.process_job(
                resume_text=resume_text,
                resume_path=resume_path,
                job_description=desc,
                job_title=job.get("title", ""),
                company=job.get("company", ""),
                applicant_name=applicant_name,
            )

            if ai_data.get("error"):
                # Detect daily quota - don't continue processing
                if "DAILY_LIMIT_EXCEEDED" in str(ai_data["error"]):
                    self.is_running = False  # Stop the loop
                    result["status"] = "failed"
                    result["error"] = ai_data["error"]
                    return result
                result["status"] = "failed"
                result["error"] = f"AI processing failed: {ai_data['error']}"
                return result

            match_score = ai_data.get("match_score", 0)
            result["match_score"] = match_score
            result["cover_letter"] = ai_data.get("cover_letter", "")

            # ── Apply LaTeX changes (no extra Gemini call needed) ──────────
            latex_replacements = ai_data.get("latex_replacements", {})
            tailored_path = None

            if Path(resume_path).suffix.lower() == ".tex" and latex_replacements:
                tailored_path = unified_processor.apply_latex_changes(
                    resume_path=resume_path,
                    latex_replacements=latex_replacements,
                    job_title=job.get("title", ""),
                    company=job.get("company", ""),
                )
                if tailored_path:
                    result["tailored_resume"] = tailored_path
                    result["changes_made"] = [
                        {"old": k[:80], "new": v[:80]}
                        for k, v in latex_replacements.items()
                    ]
                else:
                    result["tailored_resume"] = resume_path
            else:
                # For PDF/TXT or no replacements, use original resume
                result["tailored_resume"] = resume_path
                result["changes_made"] = []

            # ── Update job record in database ──────────────────────────────
            if job_id:
                await update_job(job_id, {
                    "match_score": match_score,
                    "status": "analyzed",
                    "keywords_missing": json.dumps(ai_data.get("missing_keywords", [])),
                })

            # ── Skip if match score genuinely too low ──────────────────────────────
            if match_score < 25:
                result["status"] = "skipped"
                result["error"] = f"Match score too low ({match_score}%) — skipped."
                return result

            # ── Save cover letter to file ──────────────────────────────────
            cover_letter_path = ""
            cover_letter_text = result.get("cover_letter", "")
            if cover_letter_text and job_id:
                try:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    company_slug = re.sub(r"[^a-zA-Z0-9]", "_", job.get("company", "unknown"))[:25]
                    title_slug = re.sub(r"[^a-zA-Z0-9]", "_", job.get("title", "job"))[:20]
                    cl_filename = f"cl_{company_slug}_{title_slug}_{timestamp}.txt"
                    cl_path = settings.COVER_LETTERS_DIR / cl_filename
                    cl_path.write_text(cover_letter_text, encoding="utf-8")
                    cover_letter_path = str(cl_path)
                    print(f"[Engine] 📝 Cover letter saved: {cl_filename}")
                except Exception as cl_err:
                    print(f"[Engine] ⚠ Could not save cover letter: {cl_err}")

            # ── Record the application ─────────────────────────────────────
            app_data = {
                "job_id": job_id,
                "resume_path": resume_path,
                "tailored_resume_path": result.get("tailored_resume", ""),
                "cover_letter_path": cover_letter_path,
                "status": "ready",
                "notes": (
                    f"Match: {match_score}%. "
                    f"Tailored: {'Yes' if tailored_path else 'No'}. "
                    f"Cover letter: {'Yes' if cover_letter_path else 'No'}."
                ),
            }
            app_id = await insert_application(app_data)

            # ── Attempt browser-based auto-submit ─────────────────────────
            apply_success = await self._attempt_apply(
                job,
                result.get("tailored_resume") or resume_path,
                result.get("cover_letter", ""),
            )

            if apply_success:
                result["status"] = "applied"
                if job_id:
                    await update_job(job_id, {"status": "applied"})
                if app_id:
                    await update_application(app_id, {
                        "status": "applied",
                        "applied_at": datetime.now().isoformat(),
                    })
            else:
                result["status"] = "ready"
                result["note"] = (
                    "Application prepared. Tailored resume and cover letter are ready. "
                    "Manual submission needed for this platform."
                )

        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"[Engine Error] Job {job_id}:\n{error_trace}")
            result["status"] = "failed"
            result["error"] = str(e)

        return result

    async def _attempt_apply(
        self, job: dict, resume_path: str, cover_letter: str = ""
    ) -> bool:
        """
        Attempt browser-based auto-submission.
        Currently supports Greenhouse and Lever.
        Returns True if submitted successfully.
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
                # Platform not supported for auto-submit yet
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
