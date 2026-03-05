"""
AI Job Agent - Unified AI Processor
Consolidates Analyze, Tailor, and Cover Letter tasks into a single AI call to save quota.
"""

import json
import asyncio
import random
import re
from typing import Dict, Any, Optional
import google.generativeai as genai
from backend.config import settings
from backend.resume.latex_parser import LaTeXResumeParser

class UnifiedAIProcessor:
    """Consolidates multiple AI tasks per job into a single Gemini call."""

    def __init__(self):
        if settings.GEMINI_API_KEY:
            genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model_name = "gemini-2.0-flash"
        self.model = genai.GenerativeModel(self.model_name)

    async def _generate_with_retry(self, prompt: str, max_retries: int = 3):
        """Helper to call Gemini with exponential backoff and quota wait."""
        for attempt in range(max_retries):
            try:
                response = await self.model.generate_content_async(prompt)
                return response
            except Exception as e:
                # Handle quota limits (429)
                if "429" in str(e) and attempt < max_retries - 1:
                    wait_time = 30 + random.uniform(0, 5)
                    print(f"[Unified Processor] Quota hit. Waiting {wait_time:.1f}s... (Attempt {attempt+1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    raise e
        return None

    async def process_job(
        self,
        resume_text: str,
        resume_path: str,
        job_description: str,
        job_title: str,
        company: str,
        applicant_name: str
    ) -> Dict[str, Any]:
        """
        Performs analysis, tailoring, and cover letter generation in ONE step.
        """
        
        # Determine if we can tailor (only LaTeX supported for now)
        is_latex = resume_path.lower().endswith(".tex")
        
        prompt = f"""You are an ATS expert and professional career coach. 
Perform three tasks for this candidate applying to {company} as {job_title}.

## RESUME:
{resume_text}

## JOB DESCRIPTION:
{job_description}

## TASKS:
1. ANALYZE: Match the resume against the job description. Give a score 0-100.
2. TAILOR: Suggest 3-5 specific bullet point changes for the resume to improve the match score. 
3. COVER LETTER: Write a 250-word ATS-friendly cover letter starting with "Dear Hiring Manager,".

## RESPONSE FORMAT:
Return ONLY a valid JSON object with the following structure:
{{
    "match_score": <int>,
    "overall_assessment": "<string>",
    "missing_keywords": [<strings>],
    "tailoring_suggestions": [
        {{ "section": "<string>", "current": "<string>", "suggested": "<string>", "reason": "<string>" }}
    ],
    "cover_letter": "<string>"
}}
"""

        try:
            response = await self._generate_with_retry(prompt)
            if not response:
                raise Exception("No response from Gemini")
            
            text = response.text.strip()
            # Clean JSON response
            if text.startswith("```"):
                text = re.sub(r"^```json\n|^```\n|```$", "", text, flags=re.MULTILINE).strip()
            
            result = json.loads(text)
            
            # If LaTeX, we could technically auto-apply the tailoring here, 
            # but for simplicity and safety, we'll return the result for the engine to handle.
            return result

        except Exception as e:
            print(f"[Unified Processor] Error: {e}")
            return {
                "match_score": 0,
                "error": str(e),
                "overall_assessment": "Unified processing failed."
            }

# Singleton
unified_processor = UnifiedAIProcessor()
