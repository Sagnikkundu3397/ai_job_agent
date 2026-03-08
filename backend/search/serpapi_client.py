"""
AI Job Agent - SerpAPI Client
Searches for jobs using SerpAPI's dedicated Google Jobs engine.
Returns structured job data with full descriptions, company names, and apply links.
"""

import asyncio
import httpx
import re
from typing import Optional
from backend.config import settings


class SerpAPIClient:
    """Client for searching jobs via SerpAPI Google Jobs engine."""

    BASE_URL = "https://serpapi.com/search.json"

    def __init__(self):
        self.api_key = settings.SERPAPI_KEY

    def _build_query(
        self,
        job_title: str,
        location: str = "",
        job_type: str = "",
        exclude_terms: list = None,
    ) -> str:
        """Build a natural language query for Google Jobs."""
        titles = [t.strip() for t in job_title.split(",") if t.strip()]
        query = " OR ".join(titles) if len(titles) > 1 else (titles[0] if titles else "")

        if location:
            locs = [l.strip() for l in location.split(",") if l.strip()]
            query += " " + " OR ".join(locs)

        if job_type:
            query += f" {job_type}"

        if exclude_terms:
            query += " " + " ".join(f"-{t}" for t in exclude_terms)

        return query.strip()

    def _employment_type_chip(self, job_type: str) -> str:
        """Convert job_type string to Google Jobs chip filter."""
        mapping = {
            "fulltime": "employment_type:FULLTIME",
            "full-time": "employment_type:FULLTIME",
            "full time": "employment_type:FULLTIME",
            "parttime": "employment_type:PARTTIME",
            "part-time": "employment_type:PARTTIME",
            "part time": "employment_type:PARTTIME",
            "internship": "employment_type:INTERN",
            "intern": "employment_type:INTERN",
            "contractor": "employment_type:CONTRACTOR",
            "contract": "employment_type:CONTRACTOR",
            "remote": "work_from_home:1",
        }
        return mapping.get(job_type.lower().strip(), "")

    async def search(
        self,
        job_title: str,
        location: str = "",
        job_type: str = "",
        num_results: int = 20,
        date_filter: str = "",
        platforms: list = None,  # kept for API compatibility but not used in google_jobs
        exclude_terms: list = None,
    ) -> list:
        """
        Search for jobs using SerpAPI Google Jobs engine.

        Args:
            job_title: Job title to search for (can be comma-separated for multiple)
            location: Location filter (e.g., "Bangalore, Remote")
            job_type: Employment type (e.g., "Remote", "Internship", "Full-time")
            num_results: Maximum number of results
            date_filter: Time filter - 'd'=today, 'w'=week, 'm'=month, '3d'=3 days
            exclude_terms: Terms to exclude from search
        Returns:
            List of structured job dicts
        """
        query = self._build_query(job_title, location, job_type, exclude_terms)

        all_results = []
        next_page_token = None

        # Build chips for filters
        chips_parts = []
        if job_type:
            chip = self._employment_type_chip(job_type)
            if chip:
                chips_parts.append(chip)

        # Date filter chip — map all UI options to SerpAPI equivalents
        date_chip_map = {
            # Exact SerpAPI values
            "d": "date_posted:today",
            "3d": "date_posted:3days",
            "w": "date_posted:week",
            "m": "date_posted:month",
            # UI-specific options (map to nearest SerpAPI bucket)
            "m30": "date_posted:today",   # Past 30 mins → today
            "h1": "date_posted:today",    # Past 1 hour → today
            "h2": "date_posted:today",    # Past 2 hours → today
            "h3": "date_posted:today",    # Past 3 hours → today
            "h6": "date_posted:today",    # Past 6 hours → today
            "h12": "date_posted:today",   # Past 12 hours → today
            "d2": "date_posted:3days",    # Past 2 days → 3days
            "d3": "date_posted:3days",    # Past 3 days → 3days
            "y": "date_posted:month",     # Past year → month (SerpAPI max)
        }
        if date_filter and date_filter in date_chip_map:
            chips_parts.append(date_chip_map[date_filter])
        elif date_filter:
            print(f"[SerpAPI] Unknown date_filter '{date_filter}' — skipping date chip")

        chips = ",".join(chips_parts) if chips_parts else None

        async with httpx.AsyncClient(timeout=30.0) as client:
            while len(all_results) < num_results:
                # NOTE: Google Jobs API deprecated 'start', now uses next_page_token
                params = {
                    "engine": "google_jobs",
                    "q": query,
                    "api_key": self.api_key,
                    "hl": "en",
                }

                # Only add pagination token if it's not the first page
                if next_page_token:
                    params["next_page_token"] = next_page_token

                if chips:
                    params["chips"] = chips

                if location:
                    # Use first location for geo context
                    params["location"] = location.split(",")[0].strip()

                try:
                    response = await client.get(self.BASE_URL, params=params)
                    data = response.json()

                    if "error" in data:
                        print(f"[SerpAPI Error] {data['error']}")
                        break

                    job_results = data.get("jobs_results", [])
                    if not job_results:
                        print(f"[SerpAPI] No jobs_results in response. Keys: {list(data.keys())}")
                        break

                    for job_data in job_results:
                        job = self._parse_google_job(job_data)
                        if job:
                            all_results.append(job)

                    print(f"[SerpAPI] Fetched {len(job_results)} jobs (total so far: {len(all_results)})")

                    # Check if more pages available via next_page_token
                    serpapi_pagination = data.get("serpapi_pagination", {})
                    next_page_token = serpapi_pagination.get("next_page_token")
                    if not next_page_token:
                        break  # No more pages

                    await asyncio.sleep(settings.SEARCH_DELAY_SECONDS)

                except Exception as e:
                    print(f"[SerpAPI Error] {e}")
                    break

        return all_results[:num_results]

    def _parse_google_job(self, job_data: dict) -> Optional[dict]:
        """Parse a Google Jobs result into a structured job dict."""
        title = job_data.get("title", "")
        company = job_data.get("company_name", "Unknown Company")
        location = job_data.get("location", "")
        description = job_data.get("description", "")
        detected = job_data.get("detected_extensions", {})

        # Get best apply link
        apply_options = job_data.get("apply_options", [])
        url = ""
        ats_platform = "unknown"

        # Try to find a known ATS platform link first
        ats_priority = [
            "greenhouse.io", "lever.co", "myworkdayjobs.com",
            "icims.com", "smartrecruiters.com", "breezy.hr", "jobvite.com",
            "taleo.net", "successfactors.com", "jazzhr.com",
        ]

        for opt in apply_options:
            link = opt.get("link", "")
            for plat in ats_priority:
                if plat in link:
                    url = link
                    ats_platform = plat.split(".")[0]
                    break
            if url:
                break

        # Fall back to first available apply link
        if not url and apply_options:
            url = apply_options[0].get("link", "")

        # Fall back to job listing URL from related_links
        if not url:
            related = job_data.get("related_links", [])
            if related:
                url = related[0].get("link", "")

        if not url and not title:
            return None

        # Detect platform from URL if not already found
        if ats_platform == "unknown" and url:
            for plat in ats_priority:
                if plat in url:
                    ats_platform = plat.split(".")[0]
                    break

        # Build a rich description
        desc_parts = [description]
        if detected.get("work_from_home"):
            desc_parts.append("Work from home: Yes")
        if detected.get("schedule_type"):
            desc_parts.append(f"Schedule: {detected['schedule_type']}")
        if detected.get("salary"):
            desc_parts.append(f"Salary: {detected['salary']}")
        if detected.get("posted_at"):
            desc_parts.append(f"Posted: {detected['posted_at']}")

        full_description = "\n\n".join(p for p in desc_parts if p)

        return {
            "title": title,
            "company": company,
            "location": location,
            "url": url,
            "description": full_description,
            "ats_platform": ats_platform,
            "employment_type": detected.get("schedule_type", ""),
            "salary": detected.get("salary", ""),
            "posted_at": detected.get("posted_at", ""),
            "work_from_home": detected.get("work_from_home", False),
        }


# Singleton
serpapi_client = SerpAPIClient()
