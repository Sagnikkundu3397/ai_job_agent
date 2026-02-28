"""
AI Job Agent - Job Page Parser
Scrapes individual job pages to extract full job descriptions from ATS platforms.
"""

import httpx
from bs4 import BeautifulSoup
from typing import Optional
import asyncio
import re


class JobParser:
    """Parses job listing pages to extract full job descriptions."""

    # CSS selectors for common ATS platforms
    PLATFORM_SELECTORS = {
        "greenhouse": [
            "#content",
            ".job-post",
            '[class*="job"]',
            "main",
        ],
        "lever": [
            ".posting-page",
            '[class*="posting"]',
            ".content",
            "main",
        ],
        "workday": [
            '[data-automation-id="jobPostingDescription"]',
            ".job-description",
            "main",
        ],
        "icims": [
            ".iCIMS_JobContent",
            ".job-description",
            "#job-content",
        ],
        "smartrecruiters": [
            ".job-sections",
            ".jobad-main",
            "main",
        ],
        "default": [
            '[class*="description"]',
            '[class*="job-detail"]',
            '[id*="description"]',
            "article",
            "main",
            ".content",
        ],
    }

    async def fetch_job_description(self, url: str, platform: str = "default") -> Optional[str]:
        """
        Fetch and extract the job description from a job listing URL.

        Args:
            url: The job listing URL
            platform: The ATS platform identifier

        Returns:
            Extracted job description text, or None if failed
        """
        try:
            async with httpx.AsyncClient(
                timeout=15.0,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                },
            ) as client:
                response = await client.get(url)
                if response.status_code != 200:
                    return None

                return self._extract_description(response.text, platform)

        except Exception as e:
            print(f"[JobParser Error] Failed to fetch {url}: {e}")
            return None

    def _extract_description(self, html: str, platform: str) -> Optional[str]:
        """Extract job description text from HTML."""
        soup = BeautifulSoup(html, "lxml")

        # Remove script and style elements
        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.decompose()

        # Try platform-specific selectors first, then default
        selectors = self.PLATFORM_SELECTORS.get(platform, [])
        selectors.extend(self.PLATFORM_SELECTORS["default"])

        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                text = element.get_text(separator="\n", strip=True)
                if len(text) > 100:  # Meaningful content
                    return self._clean_description(text)

        # Fallback: get body text
        body = soup.find("body")
        if body:
            text = body.get_text(separator="\n", strip=True)
            return self._clean_description(text[:3000])

        return None

    def _clean_description(self, text: str) -> str:
        """Clean and normalize the extracted description text."""
        # Remove excessive whitespace
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        text = "\n".join(lines)

        # Remove very long lines (likely encoded data)
        lines = [line for line in text.split("\n") if len(line) < 500]
        text = "\n".join(lines)

        # Limit total length
        if len(text) > 3000:
            text = text[:3000] + "..."

        return text

    async def enrich_jobs(self, jobs: list) -> list:
        """
        Enrich a list of jobs by fetching full descriptions.

        Args:
            jobs: List of job dicts with 'url' and 'ats_platform' keys

        Returns:
            Same list with 'description' field updated
        """
        tasks = []
        for job in jobs:
            tasks.append(self._enrich_single(job))

        # Process in batches of 3 to avoid rate limiting
        batch_size = 3
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i : i + batch_size]
            await asyncio.gather(*batch)
            if i + batch_size < len(tasks):
                await asyncio.sleep(1)

        return jobs

    async def _enrich_single(self, job: dict):
        """Enrich a single job with its full description."""
        if job.get("description") and len(job["description"]) > 200:
            return  # Already has a good description

        description = await self.fetch_job_description(
            job["url"], job.get("ats_platform", "default")
        )
        if description:
            job["description"] = description


# Singleton
job_parser = JobParser()
