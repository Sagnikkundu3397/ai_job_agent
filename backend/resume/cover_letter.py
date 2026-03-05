import os
import asyncio
import random
from pathlib import Path
import google.generativeai as genai
from backend.config import settings

class CoverLetterGenerator:
    """Generates ATS-friendly cover letters tailored to a job description."""

    def __init__(self):
        self.model_name = "gemini-2.0-flash"
        if settings.GEMINI_API_KEY:
            genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel(self.model_name)

    async def _generate_with_retry(self, prompt: str, max_retries: int = 3):
        """Helper to call Gemini with exponential backoff."""
        for attempt in range(max_retries):
            try:
                response = await self.model.generate_content_async(prompt)
                return response
            except Exception as e:
                if "429" in str(e) and attempt < max_retries - 1:
                    wait_time = 30 + random.uniform(0, 5)
                    print(f"[Gemini CoverLetter] Quota hit. Waiting {wait_time:.1f}s to reset RPM... (Attempt {attempt+1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    raise e
        return None

    async def generate(self, resume_text: str, job_description: str, job_title: str, company: str, applicant_name: str) -> str:
        """
        Generate a cover letter based on resume and job description.
        Returns the cover letter text.
        """
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not set")

        prompt = f"""
You are an expert career coach and professional copywriter.
Please write a concise, compelling, and ATS-friendly cover letter for the following position.
Do not include any placeholders like [Your Address] or [Date] at the top, just format it clearly starting with "Dear Hiring Manager," or similar.
Keep it under 350 words. Focus on the value the candidate brings to the specific role requirements based on their resume.

Applicant Name: {applicant_name}
Job Title: {job_title}
Company: {company}

Resume Text:
{resume_text}

Job Description:
{job_description}
"""
        try:
            response = await self._generate_with_retry(prompt)
            if not response:
                raise Exception("No response from Gemini after retries")
            return response.text.strip()
        except Exception as e:
            print(f"[CoverLetterGenerator] Error: {e}")
            return f"Dear Hiring Team,\n\nI am very interested in the {job_title} position at {company}. Please find my resume attached. I look forward to discussing how my skills and experiences align with your team's needs.\n\nSincerely,\n{applicant_name}"

cover_letter_generator = CoverLetterGenerator()
