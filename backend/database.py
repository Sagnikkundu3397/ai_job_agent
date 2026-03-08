"""
AI Job Agent - Database Layer
SQLite database setup with async support for jobs, applications, and settings.
"""

import aiosqlite
import json
from datetime import datetime
from pathlib import Path
from backend.config import settings

DB_PATH = str(settings.DB_PATH)


async def init_db():
    """Initialize the database and create tables."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT DEFAULT '',
                url TEXT NOT NULL UNIQUE,
                description TEXT DEFAULT '',
                ats_platform TEXT DEFAULT '',
                match_score REAL DEFAULT 0,
                keywords_missing TEXT DEFAULT '[]',
                status TEXT DEFAULT 'found',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                resume_path TEXT DEFAULT '',
                tailored_resume_path TEXT DEFAULT '',
                cover_letter_path TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                notes TEXT DEFAULT '',
                applied_at TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (job_id) REFERENCES jobs(id)
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                location TEXT DEFAULT '',
                results_count INTEGER DEFAULT 0,
                searched_at TEXT DEFAULT (datetime('now'))
            );
        """)
        await db.commit()


async def get_db():
    """Get a database connection."""
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db


# ========================
# Job Operations
# ========================

async def insert_job(job_data: dict) -> int:
    """Insert a new job listing. Returns the job ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """INSERT OR IGNORE INTO jobs (title, company, location, url, description, ats_platform, status)
               VALUES (?, ?, ?, ?, ?, ?, 'found')""",
            (
                job_data.get("title", ""),
                job_data.get("company", ""),
                job_data.get("location", ""),
                job_data.get("url", ""),
                job_data.get("description", ""),
                job_data.get("ats_platform", ""),
            ),
        )
        await db.commit()
        return cursor.lastrowid


async def get_all_jobs(status: str = None, limit: int = 50) -> list:
    """Get all jobs, optionally filtered by status."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if status:
            cursor = await db.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_job(job_id: int) -> dict:
    """Get a single job by ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def update_job(job_id: int, updates: dict):
    """Update a job record."""
    set_clauses = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [job_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE jobs SET {set_clauses}, updated_at = datetime('now') WHERE id = ?",
            values,
        )
        await db.commit()


# ========================
# Application Operations
# ========================

async def insert_application(app_data: dict) -> int:
    """Insert a new application record."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO applications
               (job_id, resume_path, tailored_resume_path, cover_letter_path, status, notes)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                app_data.get("job_id"),
                app_data.get("resume_path", ""),
                app_data.get("tailored_resume_path", ""),
                app_data.get("cover_letter_path", ""),
                app_data.get("status", "pending"),
                app_data.get("notes", ""),
            ),
        )
        await db.commit()
        return cursor.lastrowid


async def get_application(app_id: int) -> dict:
    """Get a single application record with job details."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT a.*, j.title as job_title, j.company, j.url as job_url, j.match_score
               FROM applications a
               JOIN jobs j ON a.job_id = j.id
               WHERE a.id = ?""",
            (app_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_applications(limit: int = 50) -> list:
    """Get application history with job details."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT a.*, j.title as job_title, j.company, j.url as job_url, j.match_score
               FROM applications a
               JOIN jobs j ON a.job_id = j.id
               ORDER BY a.created_at DESC LIMIT ?""",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def update_application(app_id: int, updates: dict):
    """Update an application record."""
    set_clauses = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [app_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE applications SET {set_clauses} WHERE id = ?", values
        )
        await db.commit()


# ========================
# Settings Operations
# ========================

async def get_setting(key: str, default: str = "") -> str:
    """Get a setting value."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cursor.fetchone()
        return row["value"] if row else default


async def set_setting(key: str, value: str):
    """Set a setting value (upsert)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO settings (key, value, updated_at)
               VALUES (?, ?, datetime('now'))
               ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')""",
            (key, value),
        )
        await db.commit()


async def get_all_settings() -> dict:
    """Get all settings as a dictionary."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT key, value FROM settings")
        rows = await cursor.fetchall()
        return {row["key"]: row["value"] for row in rows}


# ========================
# Search History
# ========================

async def log_search(query: str, location: str, results_count: int):
    """Log a search to history."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO search_history (query, location, results_count) VALUES (?, ?, ?)",
            (query, location, results_count),
        )
        await db.commit()


async def get_stats() -> dict:
    """Get dashboard stats."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        jobs_cursor = await db.execute("SELECT COUNT(*) as count FROM jobs")
        jobs_count = (await jobs_cursor.fetchone())["count"]

        applied_cursor = await db.execute(
            "SELECT COUNT(*) as count FROM applications WHERE status = 'applied'"
        )
        applied_count = (await applied_cursor.fetchone())["count"]

        pending_cursor = await db.execute(
            "SELECT COUNT(*) as count FROM applications WHERE status = 'pending'"
        )
        pending_count = (await pending_cursor.fetchone())["count"]

        avg_cursor = await db.execute(
            "SELECT AVG(match_score) as avg_score FROM jobs WHERE match_score > 0"
        )
        avg_row = await avg_cursor.fetchone()
        avg_score = round(avg_row["avg_score"], 1) if avg_row["avg_score"] else 0

        return {
            "total_jobs": jobs_count,
            "applied": applied_count,
            "pending": pending_count,
            "avg_match_score": avg_score,
        }
