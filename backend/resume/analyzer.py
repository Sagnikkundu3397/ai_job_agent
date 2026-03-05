import asyncio
import random
import json
import google.generativeai as genai
from backend.config import settings


class ResumeAnalyzer:
    """Analyzes resume content against job descriptions using Gemini AI."""

    def __init__(self):
        if settings.GEMINI_API_KEY:
            genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model_name = "gemini-2.0-flash"
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
                    print(f"[Gemini Analyzer] Quota hit. Waiting {wait_time:.1f}s to reset RPM... (Attempt {attempt+1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    raise e
        return None

    async def analyze(self, resume_text: str, job_description: str) -> dict:
        """
        Analyze how well a resume matches a job description.

        Args:
            resume_text: Plain text content of the resume
            job_description: Full job description text

        Returns:
            dict with match_score, missing_keywords, suggestions, section_feedback
        """
        prompt = f"""You are an expert ATS resume analyst and career coach. Analyze the following resume against the job description.

## RESUME:
{resume_text}

## JOB DESCRIPTION:
{job_description}

## ANALYSIS REQUIRED:
Provide a detailed analysis in the following JSON format (return ONLY valid JSON, no markdown):

{{
    "match_score": <0-100 integer score>,
    "overall_assessment": "<1-2 sentence summary of how well the resume matches>",
    "missing_keywords": ["keyword1", "keyword2", ...],
    "present_keywords": ["keyword1", "keyword2", ...],
    "section_feedback": {{
        "experience": {{
            "score": <0-100>,
            "feedback": "<specific feedback>",
            "suggested_changes": ["change1", "change2"]
        }},
        "skills": {{
            "score": <0-100>,
            "feedback": "<specific feedback>",
            "missing_skills": ["skill1", "skill2"],
            "suggested_additions": ["skill1", "skill2"]
        }},
        "projects": {{
            "score": <0-100>,
            "feedback": "<specific feedback>",
            "suggested_changes": ["change1", "change2"]
        }},
        "education": {{
            "score": <0-100>,
            "feedback": "<specific feedback>"
        }}
    }},
    "priority_changes": [
        {{
            "section": "<section name>",
            "change": "<specific change to make>",
            "priority": "<high|medium|low>",
            "reason": "<why this change matters>"
        }}
    ],
    "ats_optimization_tips": ["tip1", "tip2", ...]
}}

Be specific about what keywords, technologies, and phrases from the JOB DESCRIPTION are missing from the RESUME.
Focus on actionable, concrete changes. Be honest about the match score.
"""

        try:
            response = await self._generate_with_retry(prompt)
            if not response:
                raise Exception("No response from Gemini after retries")
            text = response.text.strip()

            # Strip markdown code fences if present
            if text.startswith("```"):
                text = text.split("\n", 1)[1]  # Remove first line
                if text.endswith("```"):
                    text = text[:-3]
                elif "```" in text:
                    text = text[: text.rfind("```")]
            text = text.strip()

            result = json.loads(text)
            return result

        except json.JSONDecodeError as e:
            return {
                "match_score": 0,
                "overall_assessment": f"Failed to parse AI response: {e}",
                "missing_keywords": [],
                "present_keywords": [],
                "section_feedback": {},
                "priority_changes": [],
                "ats_optimization_tips": [],
                "raw_response": response.text if 'response' in dir() else "",
            }
        except Exception as e:
            return {
                "match_score": 0,
                "overall_assessment": f"Analysis failed: {str(e)}",
                "missing_keywords": [],
                "present_keywords": [],
                "section_feedback": {},
                "priority_changes": [],
                "ats_optimization_tips": [],
            }


# Singleton
resume_analyzer = ResumeAnalyzer()
