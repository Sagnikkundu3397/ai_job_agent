"""
AI Job Agent - Resume Tailor
Modifies resume content based on AI analysis while preserving Jake's Resume template.
"""

import json
import re
import shutil
from pathlib import Path
from datetime import datetime
import google.generativeai as genai
from backend.config import settings


class ResumeTailor:
    """
    Tailors resume content for specific job descriptions.
    CRITICAL: Only modifies text content within LaTeX commands.
    Never changes the template structure, preamble, or command definitions.
    """

    def __init__(self):
        if settings.GEMINI_API_KEY:
            genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel("gemini-2.0-flash")

    async def tailor(
        self,
        resume_path: str,
        job_description: str,
        analysis: dict,
        job_title: str = "",
        company: str = "",
    ) -> dict:
        """
        Tailor a resume for a specific job.

        Args:
            resume_path: Path to the original .tex resume file
            job_description: Full job description text
            analysis: Analysis results from ResumeAnalyzer
            job_title: Target job title
            company: Target company name

        Returns:
            dict with 'output_path' and 'changes_made'
        """
        original = Path(resume_path)
        if not original.exists():
            raise FileNotFoundError(f"Resume not found: {resume_path}")

        original_content = original.read_text(encoding="utf-8")

        # Ask AI to generate tailored content
        tailored_content = await self._generate_tailored_content(
            original_content, job_description, analysis, job_title, company
        )

        if not tailored_content:
            return {"output_path": None, "changes_made": [], "error": "AI tailoring failed"}

        # Validate that template structure is preserved
        if not self._validate_template_integrity(original_content, tailored_content):
            # If validation fails, try a safer approach
            tailored_content = await self._safe_tailor(
                original_content, job_description, analysis
            )
            if not tailored_content:
                return {
                    "output_path": None,
                    "changes_made": [],
                    "error": "Could not tailor while preserving template",
                }

        # Save the tailored resume
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        company_slug = re.sub(r"[^a-zA-Z0-9]", "_", company or "unknown")[:30]
        output_filename = f"resume_{company_slug}_{timestamp}.tex"
        output_path = settings.RESUMES_DIR / output_filename

        output_path.write_text(tailored_content, encoding="utf-8")

        # Compute changes summary
        changes = self._diff_summary(original_content, tailored_content)

        return {
            "output_path": str(output_path),
            "output_filename": output_filename,
            "changes_made": changes,
        }

    async def _generate_tailored_content(
        self,
        original_tex: str,
        job_description: str,
        analysis: dict,
        job_title: str,
        company: str,
    ) -> str:
        """Use Gemini to generate tailored resume content."""
        missing_keywords = analysis.get("missing_keywords", [])
        priority_changes = analysis.get("priority_changes", [])

        prompt = f"""You are an expert LaTeX resume writer. Your task is to modify the resume content to better match the job description while STRICTLY PRESERVING the LaTeX template structure.

## CRITICAL RULES:
1. DO NOT change ANY LaTeX command definitions (\\newcommand, \\renewcommand, etc.)
2. DO NOT change the document preamble (everything before \\begin{{document}})
3. DO NOT change the template structure (\\resumeSubheading, \\resumeItem, etc. commands must remain)
4. DO NOT add new sections or remove existing sections
5. DO NOT change the formatting, spacing, or layout commands  
6. ONLY modify the TEXT CONTENT inside the curly braces {{}} of existing commands
7. Keep the same number of bullet points (\\resumeItem entries) per section
8. The output MUST be a complete, valid LaTeX document
9. DO NOT add any explanations - return ONLY the modified .tex content

## WHAT YOU CAN CHANGE:
- Text inside \\resumeItem{{...}} — rewrite bullets to emphasize relevant skills
- Text inside \\resumeSubheading{{...}} — update titles/descriptions if genuinely applicable
- Skills listed in the Technical Skills section — add missing relevant skills
- Project descriptions — emphasize aspects relevant to the job
- DO NOT fabricate experience or skills the candidate doesn't have
- DO adapt wording and emphasis to match the job's language

## JOB TITLE: {job_title}
## COMPANY: {company}

## MISSING KEYWORDS TO INCORPORATE (where truthful):
{json.dumps(missing_keywords, indent=2)}

## PRIORITY CHANGES SUGGESTED:
{json.dumps(priority_changes, indent=2)}

## JOB DESCRIPTION:
{job_description}

## ORIGINAL RESUME (.tex):
{original_tex}

## OUTPUT:
Return the complete modified .tex file content. Remember: ONLY modify text content, never template structure.
"""

        try:
            response = await self.model.generate_content_async(prompt)
            text = response.text.strip()

            # Strip markdown code fences if present
            if text.startswith("```"):
                # Remove first line (```latex or ```tex)
                text = text.split("\n", 1)[1]
                if text.endswith("```"):
                    text = text[:-3]
                elif "```" in text:
                    text = text[: text.rfind("```")]
            text = text.strip()

            return text

        except Exception as e:
            print(f"[ResumeTailor Error] AI generation failed: {e}")
            return None

    async def _safe_tailor(
        self, original_tex: str, job_description: str, analysis: dict
    ) -> str:
        """
        A safer tailoring approach that only modifies specific bullet items.
        Used as fallback if full generation corrupts the template.
        """
        prompt = f"""You are modifying a LaTeX resume. Return a JSON object mapping OLD text to NEW text for bullet point changes.

## RULES:
1. Only change text inside \\resumeItem{{}} commands
2. Only change skill lists in the Technical Skills section
3. Return a JSON object where keys are EXACT original text and values are replacement text
4. Maximum 8 changes
5. Do not fabricate skills or experiences

## ANALYSIS:
Missing keywords: {json.dumps(analysis.get('missing_keywords', []))}

## JOB DESCRIPTION (first 1000 chars):
{job_description[:1000]}

## RESUME CONTENT (between \\begin{{document}} and \\end{{document}}):
{original_tex[original_tex.find(chr(92) + 'begin{document}'):original_tex.find(chr(92) + 'end{document}')][:2000]}

Return ONLY valid JSON like: {{"old text 1": "new text 1", "old text 2": "new text 2"}}
"""

        try:
            response = await self.model.generate_content_async(prompt)
            text = response.text.strip()

            # Strip markdown code fences
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                if "```" in text:
                    text = text[: text.rfind("```")]
            text = text.strip()

            changes = json.loads(text)
            result = original_tex
            for old, new in changes.items():
                result = result.replace(old, new, 1)

            return result

        except Exception as e:
            print(f"[ResumeTailor Error] Safe tailor failed: {e}")
            return None

    def _validate_template_integrity(self, original: str, modified: str) -> bool:
        """
        Validate that the template structure wasn't changed.
        Compares preamble and command structure.
        """
        # Check preamble is identical
        orig_preamble_end = original.find("\\begin{document}")
        mod_preamble_end = modified.find("\\begin{document}")

        if orig_preamble_end == -1 or mod_preamble_end == -1:
            return False

        orig_preamble = original[:orig_preamble_end]
        mod_preamble = modified[:mod_preamble_end]

        if orig_preamble.strip() != mod_preamble.strip():
            return False

        # Check that key structural commands still exist
        structural_commands = [
            "\\resumeSubHeadingListStart",
            "\\resumeSubHeadingListEnd",
            "\\begin{document}",
            "\\end{document}",
        ]

        for cmd in structural_commands:
            if original.count(cmd) != modified.count(cmd):
                return False

        # Check section count is preserved
        orig_sections = len(re.findall(r"\\section\{", original))
        mod_sections = len(re.findall(r"\\section\{", modified))
        if orig_sections != mod_sections:
            return False

        return True

    def _diff_summary(self, original: str, modified: str) -> list:
        """Generate a human-readable summary of changes made."""
        changes = []

        # Compare line by line
        orig_lines = original.split("\n")
        mod_lines = modified.split("\n")

        for i, (ol, ml) in enumerate(zip(orig_lines, mod_lines)):
            if ol != ml:
                # Check if it's a content line (not structural)
                if "\\resumeItem" in ol or "\\textbf" in ol:
                    changes.append({
                        "line": i + 1,
                        "type": "modified",
                        "original": ol.strip()[:100],
                        "modified": ml.strip()[:100],
                    })

        return changes[:20]  # Limit to 20 changes for readability


# Singleton
resume_tailor = ResumeTailor()
