# 🤖 AI Job Agent — Automated Job Application System

> An AI-powered automation system that searches for job vacancies across 15+ ATS platforms, analyzes & tailors your resume using Google Gemini AI, and auto-submits applications — all from a sleek web dashboard.

<p align="center">
  <strong>Built by Sagnik Kundu</strong><br>
  <a href="https://www.linkedin.com/in/sagnik-kundu-77a94b357">LinkedIn</a>
</p>

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🔍 **Smart Job Search** | Searches Greenhouse, Lever, Workday, and 12+ ATS platforms via SerpAPI |
| 🤖 **AI Resume Analysis** | Uses Google Gemini to score your resume against job descriptions |
| ✏️ **Auto Resume Tailoring** | Modifies your resume content while preserving Jake's Resume LaTeX template |
| ⚡ **Auto-Apply** | Automated form filling for Greenhouse & Lever with Playwright |
| 📊 **Dashboard** | Premium dark-mode web UI with real-time stats, progress tracking, and history |
| 🎯 **Application Limit** | Set exactly how many jobs the agent should apply to |

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.10+
- API Keys:
  - [SerpAPI](https://serpapi.com) (free: 100 searches/month)
  - [Google Gemini](https://aistudio.google.com) (free tier)

### 2. Setup
```bash
cd ai_job_agent

# Create virtual environment
python -m venv venv
venv\Scripts\activate    # Windows
# source venv/bin/activate  # Mac/Linux

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers (for auto-apply)
python -m playwright install chromium

# Configure API keys
copy .env.example .env
# Edit .env and add your API keys
```

### 3. Run
```bash
python -m backend.main
```
Open **http://localhost:8000** in your browser.

## 📁 Project Structure

```
ai_job_agent/
├── backend/
│   ├── main.py              # FastAPI server
│   ├── config.py             # Environment config
│   ├── database.py           # SQLite models
│   ├── search/
│   │   ├── serpapi_client.py  # ATS platform search
│   │   └── job_parser.py     # Job description scraper
│   ├── resume/
│   │   ├── latex_parser.py   # Jake's Resume parser
│   │   ├── analyzer.py       # AI resume analyzer
│   │   └── tailor.py         # Resume tailoring engine
│   ├── apply/
│   │   ├── engine.py         # Auto-apply orchestrator
│   │   ├── greenhouse.py     # Greenhouse form filler
│   │   └── lever.py          # Lever form filler
│   └── templates/
│       └── resume_template.tex
├── frontend/
│   ├── index.html            # Dashboard
│   ├── styles.css            # Dark glassmorphism UI
│   └── app.js                # Dashboard logic
├── data/                      # SQLite DB + generated resumes
├── .env.example               # API key template
└── requirements.txt
```

## 🔧 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/search` | POST | Search for jobs across ATS platforms |
| `/api/jobs` | GET | List all found jobs |
| `/api/resume/upload` | POST | Upload LaTeX resume |
| `/api/resume/analyze` | POST | AI resume analysis |
| `/api/resume/tailor` | POST | Auto-tailor resume |
| `/api/apply` | POST | Start auto-apply |
| `/api/apply/progress` | GET | Get auto-apply progress |
| `/api/history` | GET | Application history |
| `/api/stats` | GET | Dashboard statistics |

## 🛡️ Security Note

**Never commit your `.env` file** with API keys. The `.gitignore` is already configured to exclude it.

## 📜 License

MIT License — Built with ❤️ by Sagnik Kundu
