/**
 * AI Job Agent — Dashboard Application Logic
 * Handles all UI interactions and API calls to the backend.
 */

// ========================
// State
// ========================

const API_BASE = '';  // Same origin
const state = {
    jobs: [],
    selectedJobs: new Set(),
    currentResumePath: '',
    allPlatforms: [
        'workforcenow.adp.com', 'bamboohr.co', 'brassring.com', 'breezy.hr',
        'bullhorn.com', 'greenhouse.io', 'icims.com', 'jazzhr.com',
        'jobdiva.com', 'jobvite.com', 'lever.co', 'successfactors.com',
        'smartrecruiters.com', 'taleo.net', 'myworkdayjobs.com'
    ],
    activePlatforms: new Set(),
    progressInterval: null,
};

// Initialize all platforms as active
state.allPlatforms.forEach(p => state.activePlatforms.add(p));


// ========================
// Initialization
// ========================

document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initPlatformChips();
    initAutocomplete();
    initResumeUpload();
    checkApiHealth();
    loadStats();
    loadHistory();

    // Refresh stats every 30 seconds
    setInterval(loadStats, 30000);
});


// ========================
// Tab Navigation
// ========================

function initTabs() {
    const tabBtns = document.querySelectorAll('.tab-btn');
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabId = btn.dataset.tab;
            switchTab(tabId);
        });
    });
}

function switchTab(tabId) {
    // Deactivate all
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

    // Activate selected
    document.querySelector(`[data-tab="${tabId}"]`).classList.add('active');
    document.getElementById(`${tabId}Tab`).classList.add('active');

    // Load data for specific tabs
    if (tabId === 'history') loadHistory();
}


// ========================
// Platform Chips
// ========================

function initPlatformChips() {
    const container = document.getElementById('platformChips');
    const platformNames = {
        'workforcenow.adp.com': 'ADP',
        'bamboohr.co': 'BambooHR',
        'brassring.com': 'BrassRing',
        'breezy.hr': 'Breezy HR',
        'bullhorn.com': 'Bullhorn',
        'greenhouse.io': 'Greenhouse',
        'icims.com': 'iCIMS',
        'jazzhr.com': 'JazzHR',
        'jobdiva.com': 'JobDiva',
        'jobvite.com': 'Jobvite',
        'lever.co': 'Lever',
        'successfactors.com': 'SAP SF',
        'smartrecruiters.com': 'SmartRecruiters',
        'taleo.net': 'Taleo',
        'myworkdayjobs.com': 'Workday'
    };

    container.innerHTML = state.allPlatforms.map(domain => `
        <div class="platform-chip active" data-domain="${domain}" onclick="togglePlatform(this, '${domain}')">
            <span class="chip-dot"></span>
            ${platformNames[domain] || domain}
        </div>
    `).join('');
}

function togglePlatform(el, domain) {
    if (state.activePlatforms.has(domain)) {
        state.activePlatforms.delete(domain);
        el.classList.remove('active');
    } else {
        state.activePlatforms.add(domain);
        el.classList.add('active');
    }
}

function toggleAllPlatforms() {
    const chips = document.querySelectorAll('.platform-chip');
    const allActive = state.activePlatforms.size === state.allPlatforms.length;

    chips.forEach(chip => {
        const domain = chip.dataset.domain;
        if (allActive) {
            state.activePlatforms.delete(domain);
            chip.classList.remove('active');
        } else {
            state.activePlatforms.add(domain);
            chip.classList.add('active');
        }
    });
}


// ========================
// Autocomplete
// ========================

const JOB_SUGGESTIONS = [
    // AI / ML / Data
    "AI / ML Engineer", "Artificial Intelligence Engineer", "Machine Learning Engineer",
    "Data Scientist", "Data Analyst", "Data Engineer", "Deep Learning Engineer",
    "NLP Engineer", "Computer Vision Engineer", "Prompt Engineer",
    // Software Eng
    "Software Engineer", "Software Developer", "Frontend Developer", "Backend Developer",
    "Full Stack Developer", "Mobile Developer", "iOS Developer", "Android Developer",
    // Cloud / DevOps
    "DevOps Engineer", "Cloud Architect", "Cloud Engineer", "Site Reliability Engineer (SRE)",
    // Security / Network
    "Cybersecurity Analyst", "Security Engineer", "Network Engineer",
    // Product / Design
    "Product Manager", "Project Manager", "UX/UI Designer", "Product Designer",
    // QA / Testing
    "QA Engineer", "Automation Tester"
];

function initAutocomplete() {
    const input = document.getElementById('jobTitle');
    const datalist = document.getElementById('jobSuggestions');

    input.addEventListener('input', function () {
        const val = this.value.toLowerCase().trim();
        datalist.innerHTML = '';

        if (!val) return;

        // Find matching job roles (case-insensitive substring match)
        const matches = JOB_SUGGESTIONS.filter(job => job.toLowerCase().includes(val));

        matches.forEach(match => {
            const option = document.createElement('option');
            option.value = match;
            datalist.appendChild(option);
        });
    });
}


// ========================
// Job Search
// ========================

async function searchJobs() {
    const jobTitle = document.getElementById('jobTitle').value.trim();
    if (!jobTitle) {
        showToast('Please enter a job title', 'warning');
        return;
    }

    const location = document.getElementById('location').value.trim();
    const jobType = document.getElementById('jobType').value;
    const numResults = parseInt(document.getElementById('numResults').value);
    const dateFilter = document.getElementById('dateFilter').value;

    const searchBtn = document.getElementById('searchBtn');
    searchBtn.disabled = true;
    searchBtn.innerHTML = '<span class="spinner"></span> Searching...';

    try {
        const response = await fetch(`${API_BASE}/api/search`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                job_title: jobTitle,
                location: location,
                job_type: jobType,
                num_results: numResults,
                date_filter: dateFilter,
                platforms: Array.from(state.activePlatforms),
                enrich: true
            })
        });

        const data = await response.json();

        if (!response.ok) {
            showToast(data.detail || 'Search failed', 'error');
            return;
        }

        state.jobs = data.jobs || [];
        renderJobResults(state.jobs);
        loadStats();
        showToast(`Found ${state.jobs.length} jobs!`, 'success');

    } catch (err) {
        showToast(`Search error: ${err.message}`, 'error');
    } finally {
        searchBtn.disabled = false;
        searchBtn.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
            </svg>
            Search Jobs`;
    }
}

function clearSearch() {
    document.getElementById('jobTitle').value = '';
    document.getElementById('location').value = '';
    state.jobs = [];
    state.selectedJobs.clear();
    document.getElementById('jobGrid').innerHTML = `
        <div class="empty-state">
            <div class="empty-icon">🚀</div>
            <h3>Ready to find your next opportunity</h3>
            <p>Enter a job title and hit search to discover vacancies across 15+ ATS platforms</p>
        </div>`;
    document.getElementById('resultsTitle').textContent = 'Results';
    document.getElementById('analyzeAllBtn').style.display = 'none';
    document.getElementById('selectAllBtn').style.display = 'none';
}

function renderJobResults(jobs) {
    const grid = document.getElementById('jobGrid');
    const title = document.getElementById('resultsTitle');

    if (!jobs.length) {
        grid.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">😔</div>
                <h3>No jobs found</h3>
                <p>Try different keywords or broaden your location filter</p>
            </div>`;
        title.textContent = 'No Results';
        return;
    }

    title.textContent = `${jobs.length} Jobs Found`;
    document.getElementById('analyzeAllBtn').style.display = 'inline-flex';
    document.getElementById('selectAllBtn').style.display = 'inline-flex';

    grid.innerHTML = jobs.map((job, i) => {
        const score = job.match_score || 0;
        const scoreClass = score >= 70 ? 'high' : score >= 40 ? 'medium' : score > 0 ? 'low' : 'none';
        const isSelected = state.selectedJobs.has(job.id);

        return `
            <div class="job-card ${isSelected ? 'selected' : ''}" id="job-${job.id}" onclick="toggleJobSelection(${job.id})">
                <div class="job-checkbox"></div>
                <div class="job-info">
                    <div class="job-title" title="${escapeHtml(job.title)}">${escapeHtml(job.title)}</div>
                    <div class="job-company">${escapeHtml(job.company)}</div>
                    <div class="job-meta">
                        <span>📍 ${escapeHtml(job.location || 'Not specified')}</span>
                        <span>🏢 ${escapeHtml(job.ats_platform || 'Unknown')}</span>
                    </div>
                </div>
                <div class="job-score">
                    <div class="score-ring ${scoreClass}">
                        ${score > 0 ? score + '%' : '—'}
                    </div>
                </div>
                <div class="job-actions">
                    <button class="job-action-btn" onclick="event.stopPropagation(); analyzeJob(${job.id})" title="Analyze">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>
                        </svg>
                    </button>
                    <button class="job-action-btn" onclick="event.stopPropagation(); tailorResume(${job.id})" title="Tailor Resume">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
                        </svg>
                    </button>
                    <a class="job-action-btn" href="${escapeHtml(job.url)}" target="_blank" onclick="event.stopPropagation()" title="Open">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                            <polyline points="15,3 21,3 21,9"/><line x1="10" y1="14" x2="21" y2="3"/>
                        </svg>
                    </a>
                </div>
            </div>`;
    }).join('');
}


// ========================
// Job Selection
// ========================

function toggleJobSelection(jobId) {
    if (state.selectedJobs.has(jobId)) {
        state.selectedJobs.delete(jobId);
    } else {
        state.selectedJobs.add(jobId);
    }

    const card = document.getElementById(`job-${jobId}`);
    if (card) card.classList.toggle('selected');

    updateSelectedJobsUI();
}

function selectAllJobs() {
    const allSelected = state.selectedJobs.size === state.jobs.length;

    state.jobs.forEach(job => {
        if (allSelected) {
            state.selectedJobs.delete(job.id);
        } else {
            state.selectedJobs.add(job.id);
        }
        const card = document.getElementById(`job-${job.id}`);
        if (card) {
            if (allSelected) card.classList.remove('selected');
            else card.classList.add('selected');
        }
    });

    updateSelectedJobsUI();
}

function updateSelectedJobsUI() {
    const count = state.selectedJobs.size;
    const countEl = document.getElementById('selectedJobsCount');
    const listEl = document.getElementById('selectedJobsList');

    countEl.textContent = `${count} job${count !== 1 ? 's' : ''} selected for auto-apply`;

    if (count === 0) {
        listEl.innerHTML = '<p class="text-muted">Select jobs from the Search tab first</p>';
    } else {
        const selectedJobs = state.jobs.filter(j => state.selectedJobs.has(j.id));
        listEl.innerHTML = selectedJobs.map(j => `
            <div class="sj-item">
                <span>${escapeHtml(j.title)}</span>
                <span class="text-muted">${escapeHtml(j.company)}</span>
            </div>
        `).join('');
    }
}


// ========================
// Resume Upload
// ========================

function initResumeUpload() {
    const dropZone = document.getElementById('resumeDropZone');
    const fileInput = document.getElementById('resumeFile');

    // Drag and drop
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('drag-over');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('drag-over');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        const files = e.dataTransfer.files;
        if (files.length) uploadResume(files[0]);
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length) uploadResume(e.target.files[0]);
    });
}

async function uploadResume(file) {
    if (!file.name.endsWith('.tex') && !file.name.endsWith('.txt')) {
        showToast('Please upload a .tex file (Jake\'s Resume template)', 'warning');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
        showToast('Uploading resume...', 'info');

        const response = await fetch(`${API_BASE}/api/resume/upload`, {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (!response.ok) {
            showToast(data.detail || 'Upload failed', 'error');
            return;
        }

        state.currentResumePath = data.path;

        // Show status
        document.getElementById('resumeStatus').style.display = 'block';
        document.getElementById('resumeFileName').textContent = file.name;
        document.getElementById('resumeSections').textContent =
            `Sections: ${(data.sections || []).join(', ')}`;

        // Show preview
        if (data.preview) {
            document.getElementById('resumePreview').style.display = 'block';
            document.getElementById('resumePreviewText').textContent = data.preview;
        }

        showToast('Resume uploaded successfully! ✅', 'success');

    } catch (err) {
        showToast(`Upload error: ${err.message}`, 'error');
    }
}


// ========================
// Resume Analysis
// ========================

async function analyzeJob(jobId) {
    showToast('Analyzing resume against job description...', 'info');

    try {
        const response = await fetch(`${API_BASE}/api/resume/analyze`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                job_id: jobId,
                resume_path: state.currentResumePath || null
            })
        });

        const data = await response.json();

        if (!response.ok) {
            showToast(data.detail || 'Analysis failed', 'error');
            return;
        }

        // Update job card with score
        const job = state.jobs.find(j => j.id === jobId);
        if (job) {
            job.match_score = data.analysis.match_score;
            renderJobResults(state.jobs);
        }

        // Show analysis results
        showAnalysis(data);
        switchTab('resume');
        showToast(`Match score: ${data.analysis.match_score}%`,
            data.analysis.match_score >= 70 ? 'success' : 'warning');

    } catch (err) {
        showToast(`Analysis error: ${err.message}`, 'error');
    }
}

async function analyzeAll() {
    const jobsToAnalyze = state.selectedJobs.size > 0
        ? state.jobs.filter(j => state.selectedJobs.has(j.id))
        : state.jobs.slice(0, 5);

    showToast(`Analyzing ${jobsToAnalyze.length} jobs...`, 'info');

    for (const job of jobsToAnalyze) {
        await analyzeJob(job.id);
        await sleep(1000);
    }

    showToast('Analysis complete!', 'success');
    loadStats();
}

function showAnalysis(data) {
    const panel = document.getElementById('analysisPanel');
    const content = document.getElementById('analysisContent');
    const analysis = data.analysis;

    const score = analysis.match_score || 0;
    const scoreClass = score >= 70 ? 'high' : score >= 40 ? 'medium' : 'low';

    content.innerHTML = `
        <div class="analysis-result">
            <div class="analysis-score-big">
                <div class="big-score ${scoreClass}">${score}%</div>
                <div class="score-label">Match Score for ${escapeHtml(data.job_title)} at ${escapeHtml(data.company)}</div>
                <p style="margin-top: 12px; font-size: 14px; color: var(--text-secondary);">
                    ${escapeHtml(analysis.overall_assessment || '')}
                </p>
            </div>

            ${analysis.missing_keywords?.length ? `
                <div class="analysis-section">
                    <h4>⚠️ Missing Keywords</h4>
                    <div class="keyword-tags">
                        ${analysis.missing_keywords.map(k => `<span class="keyword-tag missing">${escapeHtml(k)}</span>`).join('')}
                    </div>
                </div>
            ` : ''}

            ${analysis.present_keywords?.length ? `
                <div class="analysis-section">
                    <h4>✅ Present Keywords</h4>
                    <div class="keyword-tags">
                        ${analysis.present_keywords.map(k => `<span class="keyword-tag present">${escapeHtml(k)}</span>`).join('')}
                    </div>
                </div>
            ` : ''}

            ${analysis.priority_changes?.length ? `
                <div class="analysis-section">
                    <h4>📝 Suggested Changes</h4>
                    ${analysis.priority_changes.map(c => `
                        <div class="change-item">
                            <span class="change-priority ${c.priority}">${c.priority}</span>
                            <div class="change-detail">
                                <strong>${escapeHtml(c.section)}</strong>
                                <p>${escapeHtml(c.change)}</p>
                                <p style="font-style: italic; margin-top: 4px;">${escapeHtml(c.reason || '')}</p>
                            </div>
                        </div>
                    `).join('')}
                </div>
            ` : ''}

            ${analysis.ats_optimization_tips?.length ? `
                <div class="analysis-section">
                    <h4>💡 ATS Optimization Tips</h4>
                    <ul style="padding-left: 20px; font-size: 13px; color: var(--text-secondary); line-height: 1.8;">
                        ${analysis.ats_optimization_tips.map(t => `<li>${escapeHtml(t)}</li>`).join('')}
                    </ul>
                </div>
            ` : ''}
        </div>
    `;

    panel.style.display = 'block';
}


// ========================
// Resume Tailoring
// ========================

async function tailorResume(jobId) {
    showToast('Tailoring resume for this job...', 'info');

    try {
        const response = await fetch(`${API_BASE}/api/resume/tailor`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                job_id: jobId,
                resume_path: state.currentResumePath || null
            })
        });

        const data = await response.json();

        if (!response.ok) {
            showToast(data.detail || 'Tailoring failed', 'error');
            return;
        }

        const result = data.tailor_result;
        if (result.output_path) {
            showToast(`Resume tailored! Score: ${data.match_score}%. Saved: ${result.output_filename}`, 'success');
        } else {
            showToast(`Tailoring issue: ${result.error || 'Unknown error'}`, 'warning');
        }

    } catch (err) {
        showToast(`Tailor error: ${err.message}`, 'error');
    }
}


// ========================  
// Auto-Apply
// ========================

function updateRangeValue() {
    const value = document.getElementById('maxApplications').value;
    document.getElementById('rangeValue').textContent = value;
}

async function startAutoApply() {
    if (state.selectedJobs.size === 0) {
        showToast('Please select jobs from the Search tab first', 'warning');
        return;
    }

    const maxApplications = parseInt(document.getElementById('maxApplications').value);
    const jobIds = Array.from(state.selectedJobs);

    // Save settings
    const name = document.getElementById('cfgName').value;
    const email = document.getElementById('cfgEmail').value;
    const phone = document.getElementById('cfgPhone').value;
    const linkedin = document.getElementById('cfgLinkedIn').value;

    if (name || email || phone || linkedin) {
        await fetch(`${API_BASE}/api/settings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                applicant_name: name || null,
                applicant_email: email || null,
                applicant_phone: phone || null,
                linkedin_url: linkedin || null,
                max_applications: maxApplications
            })
        });
    }

    try {
        const response = await fetch(`${API_BASE}/api/apply`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                job_ids: jobIds,
                max_applications: maxApplications,
                resume_path: state.currentResumePath || null
            })
        });

        const data = await response.json();

        if (!response.ok) {
            showToast(data.detail || 'Failed to start auto-apply', 'error');
            return;
        }

        showToast(`Auto-apply started for ${data.total_jobs} jobs!`, 'success');

        // Show progress UI
        document.getElementById('startApplyBtn').style.display = 'none';
        document.getElementById('stopApplyBtn').style.display = 'inline-flex';
        document.getElementById('progressPanel').style.display = 'block';

        // Start polling progress
        startProgressPolling();

    } catch (err) {
        showToast(`Auto-apply error: ${err.message}`, 'error');
    }
}

async function stopAutoApply() {
    try {
        await fetch(`${API_BASE}/api/apply/stop`, { method: 'POST' });
        showToast('Auto-apply stopped', 'info');
        stopProgressPolling();
        document.getElementById('startApplyBtn').style.display = 'inline-flex';
        document.getElementById('stopApplyBtn').style.display = 'none';
    } catch (err) {
        showToast(`Stop error: ${err.message}`, 'error');
    }
}

function startProgressPolling() {
    state.progressInterval = setInterval(async () => {
        try {
            const response = await fetch(`${API_BASE}/api/apply/progress`);
            const progress = await response.json();

            updateProgressUI(progress);

            if (progress.status === 'completed' || progress.status === 'stopped') {
                stopProgressPolling();
                document.getElementById('startApplyBtn').style.display = 'inline-flex';
                document.getElementById('stopApplyBtn').style.display = 'none';
                loadStats();
                loadHistory();
                showToast('Auto-apply finished!', 'success');
            }
        } catch (err) {
            console.error('Progress polling error:', err);
        }
    }, 2000);
}

function stopProgressPolling() {
    if (state.progressInterval) {
        clearInterval(state.progressInterval);
        state.progressInterval = null;
    }
}

function updateProgressUI(progress) {
    const bar = document.getElementById('progressBar');
    const status = document.getElementById('progressStatus');
    const detail = document.getElementById('progressDetail');
    const log = document.getElementById('progressLog');

    const pct = progress.total > 0
        ? Math.round((progress.completed / progress.total) * 100)
        : 0;

    bar.style.width = `${pct}%`;
    status.textContent = progress.status;
    detail.textContent = progress.current_job
        ? `Processing: ${progress.current_job}`
        : `${progress.completed}/${progress.total} completed`;

    if (progress.results) {
        log.innerHTML = progress.results.map(r => {
            const cls = r.status === 'applied' ? 'success' : r.status === 'failed' ? 'error' : '';
            return `<div class="log-entry ${cls}">
                [${r.status.toUpperCase()}] ${r.job_title} @ ${r.company} — Score: ${r.match_score}%
            </div>`;
        }).join('');
    }
}


// ========================
// History
// ========================

async function loadHistory() {
    try {
        const response = await fetch(`${API_BASE}/api/history`);
        const data = await response.json();

        renderHistory(data.applications || []);
    } catch (err) {
        console.error('History load error:', err);
    }
}

function renderHistory(applications) {
    const tbody = document.getElementById('historyBody');

    if (!applications.length) {
        tbody.innerHTML = `
            <tr class="empty-row">
                <td colspan="6">
                    <div class="empty-state-inline">
                        <p>No applications yet. Start by searching for jobs!</p>
                    </div>
                </td>
            </tr>`;
        return;
    }

    tbody.innerHTML = applications.map(app => `
        <tr>
            <td>${escapeHtml(app.job_title || 'Unknown')}</td>
            <td>${escapeHtml(app.company || 'Unknown')}</td>
            <td><span class="status-badge ${app.status}">${app.status}</span></td>
            <td>${app.match_score ? app.match_score + '%' : '—'}</td>
            <td>${app.applied_at ? new Date(app.applied_at).toLocaleDateString() : '—'}</td>
            <td>
                ${app.job_url ? `<a class="job-action-btn" href="${escapeHtml(app.job_url)}" target="_blank" title="View">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                        <polyline points="15,3 21,3 21,9"/><line x1="10" y1="14" x2="21" y2="3"/>
                    </svg>
                </a>` : '—'}
            </td>
        </tr>
    `).join('');
}


// ========================
// Stats & Health
// ========================

async function loadStats() {
    try {
        const response = await fetch(`${API_BASE}/api/stats`);
        const stats = await response.json();

        document.getElementById('statJobs').textContent = stats.total_jobs || 0;
        document.getElementById('statApplied').textContent = stats.applied || 0;
        document.getElementById('statPending').textContent = stats.pending || 0;
        document.getElementById('statScore').textContent = `${stats.avg_match_score || 0}%`;
    } catch (err) {
        console.error('Stats load error:', err);
    }
}

async function checkApiHealth() {
    const indicator = document.getElementById('apiStatus');
    try {
        const response = await fetch(`${API_BASE}/api/health`);
        const data = await response.json();

        const dot = indicator.querySelector('.status-dot');
        const label = indicator.querySelector('span');

        if (data.status === 'healthy') {
            dot.className = 'status-dot online';
            const features = [];
            if (data.serpapi_configured) features.push('Search');
            if (data.gemini_configured) features.push('AI');
            label.textContent = features.length ? features.join(' + ') + ' Ready' : 'API Ready';
        } else {
            dot.className = 'status-dot offline';
            label.textContent = 'API Error';
        }
    } catch (err) {
        const dot = indicator.querySelector('.status-dot');
        const label = indicator.querySelector('span');
        dot.className = 'status-dot offline';
        label.textContent = 'Offline';
    }
}


// ========================
// Toast Notifications
// ========================

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${icons[type]}</span>
        <span class="toast-message">${escapeHtml(message)}</span>
        <button class="toast-close" onclick="this.parentElement.remove()">×</button>
    `;

    container.appendChild(toast);

    // Auto-remove after 5 seconds
    setTimeout(() => {
        if (toast.parentElement) {
            toast.style.animation = 'slideInRight 0.3s ease reverse';
            setTimeout(() => toast.remove(), 300);
        }
    }, 5000);
}


// ========================
// Utilities
// ========================

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}
