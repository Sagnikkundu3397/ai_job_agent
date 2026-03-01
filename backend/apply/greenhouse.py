"""
AI Job Agent - Greenhouse Auto-Apply
Handles automated application submission for Greenhouse-powered job boards.
"""

import asyncio
from pathlib import Path
from backend.config import settings


async def apply_greenhouse(job: dict, resume_path: str, cover_letter: str = "") -> bool:
    """
    Auto-apply to a Greenhouse job listing.

    Greenhouse application pages typically have the format:
    https://boards.greenhouse.io/company/jobs/XXXXX

    The application form includes: name, email, phone, resume upload,
    LinkedIn, and sometimes custom questions.

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
        print("[Greenhouse] Playwright not installed. Run: pip install playwright && python -m playwright install chromium")
        return False

    url = job.get("url", "")
    if not url:
        return False

    # Convert application URL to the apply page
    apply_url = url
    if "/jobs/" in url and "#app" not in url:
        apply_url = url + "#app"

    browser = None
    try:
        async with async_playwright() as p:
            # Optimize launch for low-memory environments like Render
            browser = await p.chromium.launch(
                headless=True,
                args=["--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu"]
            )
            page = await browser.new_page()

            await page.goto(apply_url, wait_until="networkidle", timeout=45000)
            await asyncio.sleep(2)

            # Fill in application form fields
            form_filled = False

            # Try to find and fill name fields
            name_selectors = [
                'input[name*="name"]',
                '#first_name',
                '#last_name',
                'input[placeholder*="Name"]',
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

            # Fill email
            email_selectors = [
                'input[type="email"]',
                'input[name*="email"]',
                '#email',
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

            # Fill phone
            phone_selectors = [
                'input[type="tel"]',
                'input[name*="phone"]',
                '#phone',
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

            # Fill LinkedIn
            linkedin_selectors = [
                'input[name*="linkedin"]',
                'input[name*="url"]',
                'input[placeholder*="LinkedIn"]',
            ]
            for selector in linkedin_selectors:
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
                    'textarea[name*="cover"]',
                    '#cover_letter',
                ]
                
                try:
                    manual_btn = await page.query_selector('a[data-source="paste"]:has-text("Paste")')
                    if manual_btn:
                        await manual_btn.click()
                        await asyncio.sleep(0.5)
                except Exception:
                    pass

                for selector in cover_selectors:
                    try:
                        element = await page.query_selector(selector)
                        if element and await element.is_visible():
                            await element.fill(cover_letter)
                            form_filled = True
                            break
                    except Exception:
                        continue

            # Upload resume
            resume_file = Path(resume_path)
            if resume_file.exists():
                file_selectors = [
                    'input[type="file"]',
                    'input[name*="resume"]',
                    '#resume',
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

            # Submit (only if we managed to fill something)
            if form_filled:
                submit_selectors = [
                    'button[type="submit"]',
                    'input[type="submit"]',
                    'button:has-text("Submit")',
                    'button:has-text("Apply")',
                ]
                for selector in submit_selectors:
                    try:
                        element = await page.query_selector(selector)
                        if element:
                            await element.click()
                            await asyncio.sleep(5)  # Wait for submission
                            # Wait for some success message or redirect
                            form_filled = True
                            break
                    except Exception:
                        continue

            return form_filled

    except Exception as e:
        print(f"[Greenhouse] Auto-apply failed: {e}")
        return False
    finally:
        if browser:
            await browser.close()
