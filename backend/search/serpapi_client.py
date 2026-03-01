"""
AI Job Agent - SerpAPI Client
Searches for jobs across ATS platforms using Google search with site: operators.
"""

import asyncio
import httpx
from typing import Optional
from backend.config import settings


class SerpAPIClient:
    """Client for searching jobs via SerpAPI Google Search."""

    BASE_URL = "https://serpapi.com/search.json"

    def __init__(self):
        self.api_key = settings.SERPAPI_KEY
        self.ats_platforms = settings.ATS_PLATFORMS

    def _build_site_query(self, platforms: list = None) -> str:
        """Build the site: OR chain for Google search."""
        targets = platforms or self.ats_platforms
        site_parts = [f"site:{domain}" for domain in targets]
        return f"({' OR '.join(site_parts)})"

    def _build_search_query(
        self,
        job_title: str,
        location: str = "",
        job_type: str = "",
        exclude_terms: list = None,
        platforms: list = None,
    ) -> str:
        """
        Build a full Google search query.
        Example: (site:greenhouse.io OR site:lever.co) "software engineer" ("Bangalore" OR "remote")
        """
        site_query = self._build_site_query(platforms)
        query = f'{site_query} "{job_title}"'

        if location:
            locations = [loc.strip() for loc in location.split(",")]
            if len(locations) > 1:
                loc_query = " OR ".join(f'"{loc}"' for loc in locations)
                query += f" ({loc_query})"
            else:
                query += f' "{locations[0]}"'

        if job_type:
            query += f' "{job_type}"'

        if exclude_terms:
            for term in exclude_terms:
                query += f" -{term}"

        return query

    async def search(
        self,
        job_title: str,
        location: str = "",
        job_type: str = "",
        num_results: int = 20,
        date_filter: str = "",
        platforms: list = None,
        exclude_terms: list = None,
    ) -> list:
        """
        Search for jobs across ATS platforms.

        Args:
            job_title: Job title to search for (e.g., "software engineer intern")
            location: Location filter (e.g., "Bangalore, remote")
            num_results: Maximum number of results to fetch
            date_filter: Time filter - 'd' (day), 'w' (week), 'm' (month), 'y' (year)
            platforms: Optional list of specific ATS domains to search
            exclude_terms: Terms to exclude from search results

        Returns:
            List of job result dicts with title, link, snippet, platform
        """
        query = self._build_search_query(job_title, location, job_type, exclude_terms, platforms)

        all_results = []
        start = 0
        per_page = min(num_results, 10)  # Google returns max 10 per page

        async with httpx.AsyncClient(timeout=30.0) as client:
            while len(all_results) < num_results:
                params = {
                    "engine": "google",
                    "q": query,
                    "api_key": self.api_key,
                    "num": per_page,
                    "start": start,
                }

                if date_filter:
                    tbs_map = {
                        "m30": "qdr:n30", # past 30 minutes
                        "h1": "qdr:h",    # past hour
                        "h2": "qdr:h2",   # past 2 hours
                        "h3": "qdr:h3",   # past 3 hours
                        "h6": "qdr:h6",   # past 6 hours
                        "h12": "qdr:h12", # past 12 hours
                        "d": "qdr:d",     # past 24 hours
                        "d2": "qdr:d2",   # past 2 days
                        "d3": "qdr:d3",   # past 3 days
                        "w": "qdr:w",     # past week
                        "m": "qdr:m",     # past month
                        "y": "qdr:y",     # past year
                    }
                    if date_filter in tbs_map:
                        params["tbs"] = tbs_map[date_filter]

                try:
                    response = await client.get(self.BASE_URL, params=params)
                    data = response.json()

                    if "error" in data:
                        print(f"[SerpAPI Error] {data['error']}")
                        break

                    organic_results = data.get("organic_results", [])
                    if not organic_results:
                        break

                    for result in organic_results:
                        job = self._parse_result(result)
                        if job:
                            all_results.append(job)

                    start += per_page

                    # Rate limiting
                    await asyncio.sleep(settings.SEARCH_DELAY_SECONDS)

                except Exception as e:
                    print(f"[SerpAPI Error] {e}")
                    break

        return all_results[:num_results]

    def _parse_result(self, result: dict) -> Optional[dict]:
        """Parse a single search result into a structured job dict."""
        link = result.get("link", "")
        if not link:
            return None

        # Detect which ATS platform
        platform = "unknown"
        for domain in self.ats_platforms:
            if domain in link:
                platform = domain.split(".")[0]  # e.g., "greenhouse" from "greenhouse.io"
                break

        title = result.get("title", "")
        snippet = result.get("snippet", "")

        # Try to extract company from title or snippet
        company = self._extract_company(title, snippet, platform)

        return {
            "title": self._clean_title(title),
            "company": company,
            "location": self._extract_location(snippet),
            "url": link,
            "description": snippet,
            "ats_platform": platform,
        }

    def _clean_title(self, title: str) -> str:
        """Clean the job title from search result."""
        # Remove common suffixes like "- Company Name" or "| Greenhouse"
        for sep in [" - ", " | ", " — ", " · "]:
            if sep in title:
                title = title.split(sep)[0]
        return title.strip()

    def _extract_company(self, title: str, snippet: str, platform: str) -> str:
        """Attempt to extract company name from title/snippet."""
        # Clean title first
        clean_t = title
        for p in [" | ", " — ", " - ", " · "]:
            if p in clean_t:
                clean_t = clean_t.split(p)[0]

        # Common patterns: "Job Title @ Company", "Job Title at Company"
        for sep in [" @ ", " at ", " at: "]:
            if sep in clean_t:
                parts = clean_t.split(sep)
                if len(parts) >= 2:
                    candidate = parts[1].strip()
                    # Remove years or locations if stuck to the end
                    candidate = re.sub(r'\b(19|20)\d{2}\b', '', candidate) # Remove years
                    candidate = candidate.split(',')[0].strip() # Remove location if comma
                    if candidate and candidate.lower() not in ["greenhouse", "lever", "jobs", "hiring"]:
                        return candidate

        # Fallback to checking the title for the first part after a dash
        for sep in [" - ", " | ", " — "]:
            if sep in title:
                parts = title.split(sep)
                if len(parts) >= 2:
                    candidate = parts[1].strip()
                    if candidate.lower() not in [platform.lower(), "greenhouse", "lever", "jobs"]:
                        return candidate

        return "Unknown Company"

    def _extract_location(self, snippet: str) -> str:
        """Try to extract location from the snippet text."""
        location_keywords = [
            "remote", "hybrid", "on-site", "onsite", "bangalore", "mumbai", 
            "delhi", "hyderabad", "pune", "chennai", "kolkata", "india",
            "new york", "san francisco", "austin", "texas", "london", "usa"
        ]
        found = []
        snippet_lower = snippet.lower()
        for kw in location_keywords:
            if kw in snippet_lower:
                found.append(kw.title())
        
        # Look for "in [City]" or "[City], [State]"
        location_match = re.search(r'\bin\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', snippet)
        if location_match:
            loc = location_match.group(1)
            if loc.lower() not in ["the", "this", "our"]:
                found.append(loc)

        return ", ".join(list(set(found))) if found else ""


# Singleton
serpapi_client = SerpAPIClient()
