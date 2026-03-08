"""
AI Job Agent - Unified AI Processor
ONE Gemini call per job does everything:
  1. Resume analysis & match score
  2. Specific LaTeX bullet point replacements (actually tailors the resume)
  3. ATS-optimized 3-paragraph cover letter

This is the core quota-saver: was 2-3 calls per job, now it's 1.
"""

import json
import asyncio
import re
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
import google.generativeai as genai
from backend.config import settings
from backend.resume.latex_parser import LaTeXResumeParser


class UnifiedAIProcessor:
    """Single Gemini call handles analysis + tailoring + cover letter per job."""

    def __init__(self):
        if settings.GEMINI_API_KEY:
            genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model_name = "gemini-2.0-flash"
        self.model = genai.GenerativeModel(self.model_name)

    async def _generate_with_retry(self, prompt: str, max_retries: int = 4) -> Any:
        """Call Gemini with smart retry: reads the suggested wait time from the error."""
        for attempt in range(max_retries):
            try:
                response = await self.model.generate_content_async(prompt)
                return response
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg:
                    # Check for daily (not RPM) limit — no point in retrying
                    if "GenerateRequestsPerDay" in error_msg or "quota" in error_msg.lower():
                        print("[Unified Processor] CRITICAL: Daily API quota exceeded.")
                        raise Exception(
                            "DAILY_LIMIT_EXCEEDED: Google Free Tier daily limit (1,500 requests) "
                            "is used up. Please wait 24 hours or use a new API key in your .env file."
                        )
                    if attempt < max_retries - 1:
                        # Parse the suggested retry time from the error
                        wait_time = 35.0
                        match = re.search(r"retry[_ ]?(?:after|in)[\s_]*([\d.]+)s", error_msg, re.IGNORECASE)
                        if match:
                            wait_time = float(match.group(1)) + 3
                        print(f"[Unified Processor] Rate limit hit. Waiting {wait_time:.0f}s... (attempt {attempt+1}/{max_retries})")
                        await asyncio.sleep(wait_time)
                    else:
                        raise
                else:
                    raise
        return None

    async def process_job(
        self,
        resume_text: str,
        resume_path: str,
        job_description: str,
        job_title: str,
        company: str,
        applicant_name: str,
    ) -> Dict[str, Any]:
        """
        ONE Gemini call: Analyze + tailor bullets + write smart cover letter.
        Returns a dict with everything the engine needs.
        """
        is_latex = resume_path.lower().endswith(".tex")

        # Read the raw .tex content if applicable
        raw_tex = ""
        if is_latex:
            try:
                raw_tex = Path(resume_path).read_text(encoding="utf-8")
            except Exception:
                is_latex = False

        # Truncate long JDs to save tokens (first 3000 chars is usually enough)
        jd_trimmed = job_description[:3000] if len(job_description) > 3000 else job_description

        latex_section = ""
        if is_latex:
            # Only send the document body, not the preamble (saves tokens)
            body_start = raw_tex.find(r"\begin{document}")
            body_end = raw_tex.find(r"\end{document}")
            if body_start != -1 and body_end != -1:
                body = raw_tex[body_start:body_end + len(r"\end{document}")]
            else:
                body = raw_tex
            # Trim body to 3500 chars to stay within limits
            body_trimmed = body[:3500] if len(body) > 3500 else body
            latex_section = f"""
## LATEX RESUME BODY (for tailoring):
{body_trimmed}

## TASK 3 — LaTeX Tailoring:
Produce a JSON object "latex_replacements" where each key is the **exact** existing text 
(from inside \\resumeItem{{...}} or the skills/tech list) and the value is the improved 
replacement. Aim for 5-8 replacements that:
- Embed missing keywords from the JD naturally
- Reframe existing bullets using JD's language and action verbs
- Add quantified metrics if the context supports it
- NEVER invent new skills or fake experience
- Keep replacements the same approximate length as the original
Return an EMPTY object {{}} if no tailoring is needed (score >= 90).
"""
        else:
            latex_section = """
## TASK 3 — LaTeX Tailoring:
"latex_replacements": {}
(Tailoring skipped — not a LaTeX resume.)
"""

        prompt = f"""You are a senior ATS expert, professional resume writer, and career coach.
A candidate named **{applicant_name}** is applying for **{job_title}** at **{company}**.

---
## CANDIDATE RESUME (plain text):
{resume_text[:2500]}

---
## JOB DESCRIPTION:
{jd_trimmed}

---
## YOUR TASKS (all in ONE JSON response):

### TASK 1 — Resume Analysis:
- Score the resume's fit for this JD from 0-100 (be realistic, not generous)
- List the most important keywords/skills from the JD that are MISSING from the resume
- Write a 1-sentence overall assessment

### TASK 2 — ATS Cover Letter (3 structured paragraphs):
Write a 3-paragraph ATS-optimized cover letter for {applicant_name}:

**Paragraph 1 — Hook (50-60 words)**:
Open with the role name and company. Lead with one specific value proposition 
directly tied to the JD's most important requirement.

**Paragraph 2 — Skill Match (120-140 words)**:
Reference 2-3 SPECIFIC experiences, projects, or skills from the candidate's resume 
that directly address the JD's requirements. Use the JD's exact keywords/phrases 
naturally in sentences. Include numbers/metrics where the resume supports it.

**Paragraph 3 — Closing (50-60 words)**:
Express specific enthusiasm for the company's mission (if inferrable from the JD). 
End with a confident call to action.

Do NOT use placeholders like [Your Address] or [Date]. 
Start with "Dear Hiring Manager," and end with "Sincerely, {applicant_name}".
{latex_section}

---
## RESPONSE FORMAT:
Return ONLY a valid JSON object, no markdown fences, no explanation:
{{
    "match_score": <int 0-100>,
    "overall_assessment": "<1-sentence string>",
    "missing_keywords": ["<keyword1>", "<keyword2>", ...],
    "cover_letter": "<full cover letter as a single string with \\n for line breaks>",
    "latex_replacements": {{"<exact original text>": "<improved replacement text>", ...}}
}}
"""

        try:
            response = await self._generate_with_retry(prompt)
            if not response:
                raise Exception("No response from Gemini after retries")

            text = response.text.strip()

            # Strip markdown code fences if Gemini added them
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\n?", "", text, flags=re.MULTILINE)
                text = re.sub(r"\n?```$", "", text.strip())
            text = text.strip()

            result = json.loads(text)

            # Ensure required keys exist
            result.setdefault("match_score", 0)
            result.setdefault("missing_keywords", [])
            result.setdefault("cover_letter", "")
            result.setdefault("latex_replacements", {})
            result.setdefault("overall_assessment", "")

            print(
                f"[Unified Processor] ✓ {job_title} @ {company} | "
                f"Score: {result['match_score']}% | "
                f"Replacements: {len(result.get('latex_replacements', {}))} | "
                f"CL: {len(result.get('cover_letter', ''))} chars"
            )
            return result

        except json.JSONDecodeError as e:
            print(f"[Unified Processor] JSON parse error: {e}\nRaw response: {text[:500]}")
            return {
                "match_score": 0,
                "error": f"Failed to parse AI response as JSON: {e}",
                "missing_keywords": [],
                "cover_letter": "",
                "latex_replacements": {},
            }
        except Exception as e:
            print(f"[Unified Processor] Error: {e}")
            return {
                "match_score": 0,
                "error": str(e),
                "missing_keywords": [],
                "cover_letter": "",
                "latex_replacements": {},
            }

    def apply_latex_changes(
        self,
        resume_path: str,
        latex_replacements: dict,
        job_title: str,
        company: str,
    ) -> Optional[str]:
        """
        Apply the AI-suggested text replacements to the .tex resume.
        Saves a new job-specific file. Returns the output path, or None on failure.
        """
        if not latex_replacements:
            print(f"[Unified Processor] No replacements to apply — using original resume.")
            return None

        original = Path(resume_path)
        if not original.exists() or not original.suffix.lower() == ".tex":
            return None

        try:
            content = original.read_text(encoding="utf-8")
        except Exception as e:
            print(f"[Unified Processor] Could not read .tex file: {e}")
            return None

        changes_applied = 0
        for old_text, new_text in latex_replacements.items():
            if not old_text or not new_text:
                continue
            if old_text in content:
                content = content.replace(old_text, new_text, 1)
                changes_applied += 1
            else:
                print(f"[Unified Processor] ⚠ Replacement not found in resume: '{old_text[:60]}...'")

        if changes_applied == 0:
            print(f"[Unified Processor] ⚠ No replacements matched. Saving copy of original.")

        # Save tailored resume with a unique name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        company_slug = re.sub(r"[^a-zA-Z0-9]", "_", company or "unknown")[:25]
        title_slug = re.sub(r"[^a-zA-Z0-9]", "_", job_title or "job")[:20]
        output_filename = f"resume_{company_slug}_{title_slug}_{timestamp}.tex"
        output_path = settings.RESUMES_DIR / output_filename

        try:
            output_path.write_text(content, encoding="utf-8")
            print(f"[Unified Processor] ✓ Saved tailored resume: {output_filename} ({changes_applied} changes)")
            return str(output_path)
        except Exception as e:
            print(f"[Unified Processor] Failed to save tailored resume: {e}")
            return None


# Singleton
unified_processor = UnifiedAIProcessor()
