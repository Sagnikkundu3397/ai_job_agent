"""
AI Job Agent - Lever Auto-Apply
Handles automated application submission for Lever-powered job boards.
"""

import asyncio
from pathlib import Path
from backend.config import settings


async def apply_lever(job: dict, resume_path: str, cover_letter: str = "") -> bool:
    """
    Auto-apply to a Lever job listing.

    Lever application pages typically have the format:
    https://jobs.lever.co/company/JOB-ID/apply

    The form usually includes: name, email, phone, LinkedIn,
    resume upload, current company, and a "Why interested" field.

    Args:
        job: Job dict with 'url' key
        resume_path: Path to the resume file to upload
        cover_letter: text of cover letter

    Returns:
        True if successfully applied
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("[Lever] Playwright not installed. Run: pip install playwright && python -m playwright install chromium")
        return False

    url = job.get("url", "")
    if not url:
        return False

    # Convert to apply URL
    apply_url = url
    if "/apply" not in url:
        apply_url = url.rstrip("/") + "/apply"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            await page.goto(apply_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            form_filled = False

            # Full name
            name_selectors = [
                'input[name="name"]',
                'input[placeholder*="Full name"]',
                '.application-name input',
            ]
            for selector in name_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        await element.fill(settings.APPLICANT_NAME)
                        form_filled = True
                        break
                except Exception:
                    continue

            # Email
            email_selectors = [
                'input[name="email"]',
                'input[type="email"]',
                '.application-email input',
            ]
            for selector in email_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        await element.fill(settings.APPLICANT_EMAIL)
                        form_filled = True
                        break
                except Exception:
                    continue

            # Phone
            phone_selectors = [
                'input[name="phone"]',
                'input[type="tel"]',
                '.application-phone input',
            ]
            for selector in phone_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        await element.fill(settings.APPLICANT_PHONE)
                        form_filled = True
                        break
                except Exception:
                    continue

            # LinkedIn / URLs
            url_selectors = [
                'input[name*="urls"]',
                'input[name*="linkedin"]',
                'input[placeholder*="LinkedIn"]',
                '.application-urls input',
            ]
            for selector in url_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        await element.fill(settings.LINKEDIN_URL)
                        break
                except Exception:
                    continue

            # Fill Cover Letter if provided
            if cover_letter:
                cover_selectors = [
                    'textarea[name*="comments"]',
                    'textarea[placeholder*="Additional information"]',
                    '.application-additional input',
                ]
                for selector in cover_selectors:
                    try:
                        element = await page.query_selector(selector)
                        if element and await element.is_visible():
                            await element.fill(cover_letter)
                            form_filled = True
                            break
                    except Exception:
                        continue

            # Resume upload
            resume_file = Path(resume_path)
            if resume_file.exists():
                file_selectors = [
                    'input[type="file"]',
                    'input[name*="resume"]',
                    '.application-resume input[type="file"]',
                ]
                for selector in file_selectors:
                    try:
                        element = await page.query_selector(selector)
                        if element:
                            await element.set_input_files(str(resume_file))
                            form_filled = True
                            break
                    except Exception:
                        continue

            # Submit
            if form_filled:
                submit_selectors = [
                    'button[type="submit"]',
                    '.postings-btn-submit',
                    'button:has-text("Submit application")',
                    'button:has-text("Submit")',
                ]
                for selector in submit_selectors:
                    try:
                        element = await page.query_selector(selector)
                        if element:
                            await element.click()
                            await asyncio.sleep(3)
                            break
                    except Exception:
                        continue

            await browser.close()
            return form_filled

    except Exception as e:
        print(f"[Lever] Auto-apply failed: {e}")
        return False
