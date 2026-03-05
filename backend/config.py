"""
AI Job Agent - Configuration
Loads environment variables and provides app-wide settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    """Application settings loaded from environment variables."""

    # API Keys
    SERPAPI_KEY: str = os.getenv("SERPAPI_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")

    # Applicant Info
    APPLICANT_NAME: str = os.getenv("APPLICANT_NAME", "")
    APPLICANT_EMAIL: str = os.getenv("APPLICANT_EMAIL", "")
    APPLICANT_PHONE: str = os.getenv("APPLICANT_PHONE", "")
    LINKEDIN_URL: str = os.getenv("LINKEDIN_URL", "")

    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    # Paths
    BASE_DIR: Path = BASE_DIR
    DATA_DIR: Path = BASE_DIR / "data"
    RESUMES_DIR: Path = BASE_DIR / "data" / "resumes"
    DB_PATH: Path = BASE_DIR / "data" / "jobs.db"
    TEMPLATES_DIR: Path = Path(__file__).resolve().parent / "templates"

    # ATS Platforms to search
    ATS_PLATFORMS: list = [
        "workforcenow.adp.com",
        "bamboohr.co",
        "brassring.com",
        "breezy.hr",
        "bullhorn.com",
        "greenhouse.io",
        "icims.com",
        "jazzhr.com",
        "jobdiva.com",
        "jobvite.com",
        "lever.co",
        "successfactors.com",
        "smartrecruiters.com",
        "taleo.net",
        "myworkdayjobs.com",
    ]

    # Defaults
    DEFAULT_MAX_APPLICATIONS: int = 5
    SEARCH_DELAY_SECONDS: float = 2.0
    APPLY_DELAY_SECONDS: float = 30.0

    @classmethod
    def ensure_dirs(cls):
        """Create required directories if they don't exist."""
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.RESUMES_DIR.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
