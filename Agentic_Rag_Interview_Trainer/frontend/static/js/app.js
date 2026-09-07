/**
 * Agentic RAG Interview Trainer — Main App
 */

const MAX_QUESTIONS = 10;

// ─── State ────────────────────────────────────────────────────────────────────
const state = {
  currentPage: 'home',
  sessionId: null,
  profile: null,
  interviewType: 'mixed',
  currentQuestion: null,
  questionHistory: [],   // all generated questions, in order
  questionIndex: 0,      // currently displayed question index
  skippedQuestionIds: new Set(),
  answeredQuestionIds: new Set(),
  completedCount: 0,     // unique questions answered or skipped
  currentEvaluation: null,
  kbReady: false,
  interviewComplete: false,
  _nextInFlight: false   // debounce guard for next/skip
};

// ─── Init ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  renderApp();
  await checkHealth();
});

async function checkHealth() {
  try {
    const h = await api.health();
    state.kbReady = h.knowledge_base === 'ready';
    updateNavStatus(h.knowledge_base);
    if (!state.kbReady) {
      showToast('Building knowledge base index…', 'info');
      try {
        const kb = await api.initKB();
        state.kbReady = true;
        updateNavStatus('ready');
        showToast(`Knowledge base ready — ${kb.chunks_indexed} chunks indexed`, 'success');
      } catch (e) {
        showToast('KB init failed: ' + e.message, 'error');
      }
    }
  } catch (e) {
    updateNavStatus('offline');
    showToast('Cannot reach backend. Is the server running on :8000?', 'error');
  }
}

function updateNavStatus(status) {
  const el = document.getElementById('nav-status');
  if (!el) return;
  const map = { ready: '● KB Ready', loading: '◌ Loading KB', offline: '○ Offline' };
  el.textContent = map[status] || status;
  el.className = 'navbar-status' + (status === 'ready' ? ' ready' : '');
}

// ─── Routing ──────────────────────────────────────────────────────────────────
function navigate(page) {
  state.currentPage = page;
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  const el = document.getElementById('page-' + page);
  if (el) el.classList.add('active');
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ─── Render Shell ─────────────────────────────────────────────────────────────
function renderApp() {
  document.getElementById('app').innerHTML =
    renderNavbar() +
    `<div id="page-home"            class="page active">${renderHomePage()}</div>
     <div id="page-profile"         class="page">${renderProfilePage()}</div>
     <div id="page-interview"       class="page"></div>
     <div id="page-recommendations" class="page"></div>
     <div id="page-summary"         class="page"></div>`;
  bindProfileEvents();
}

// ─── Navbar ───────────────────────────────────────────────────────────────────
function renderNavbar() {
  return `<nav class="navbar">
    <a class="navbar-brand" onclick="navigate('home')">
      <span class="brand-icon">🎯</span>
      <span>Interview Trainer</span>
    </a>
    <div class="navbar-actions">
      <span id="nav-status" class="navbar-status">◌ Connecting…</span>
    </div>
  </nav>`;
}

// ─── Home Page ────────────────────────────────────────────────────────────────
function renderHomePage() {
  return `
  <div class="hero">
    <div class="hero-orb hero-orb-one"></div><div class="hero-orb hero-orb-two"></div>
    <div class="hero-inner">
      <div class="hero-badge"><span class="status-dot"></span> Powered by IBM Granite + RAG</div>
      <div class="hero-kicker">AI INTERVIEW COACH</div>
      <h1>Practice smarter.<br><span>Interview stronger.</span></h1>
      <p>Personalised mock interviews grounded in your role, skills and experience — with IBM Granite evaluating every answer.</p>
      <div class="hero-actions">
        <button class="btn btn-primary btn-lg hero-primary" onclick="navigate('profile')"><span>🚀</span> Start Preparing</button>
        <button class="btn btn-secondary btn-lg hero-secondary" onclick="document.getElementById('features').scrollIntoView({behavior:'smooth'})">See how it works <span>↓</span></button>
      </div>
      <div class="hero-trust">
        <span>✓ 10-question mock session</span><span>✓ RAG-grounded questions</span><span>✓ Instant AI feedback</span>
      </div>
    </div>
  </div>
  <section class="workflow-strip">
    <div class="container-wide workflow-inner">
      <div><span class="workflow-num">01</span><strong>Build your profile</strong><small>Role · level · skills</small></div>
      <span class="workflow-arrow">→</span>
      <div><span class="workflow-num">02</span><strong>Answer realistic questions</strong><small>Technical · behavioural · role-specific</small></div>
      <span class="workflow-arrow">→</span>
      <div><span class="workflow-num">03</span><strong>Get actionable feedback</strong><small>Score · gaps · model answer</small></div>
    </div>
  </section>
  <section class="features" id="features">
    <div class="container-wide">
      <div class="section-heading">
        <div><span class="eyebrow">BUILT FOR REAL PRACTICE</span><h2 class="section-title">Everything you need to improve</h2></div>
        <p class="section-sub">A focused interview workspace powered by retrieval and IBM Granite.</p>
      </div>
      <div class="features-grid">
        ${[
          ['🔍','RAG-grounded questions','Questions are generated from your profile and a curated interview knowledge base.'],
          ['🤖','IBM Granite evaluation','A structured rubric checks relevance, accuracy, completeness, specificity and communication.'],
          ['📊','Actionable scoring','See exactly what worked, what was missing and how to improve the next answer.'],
          ['🎯','Role-aware practice','Difficulty and topics adapt to your target role, experience level and skills.'],
          ['💬','Smart follow-ups','Probe deeper into your answer and practise defending your decisions.'],
          ['📋','Personal prep plan','Turn your session feedback into focused study recommendations.']
        ].map(([icon,title,desc]) => `
          <div class="feature-card">
            <div class="feature-icon-wrap"><span class="feature-icon">${icon}</span></div>
            <div><h3>${title}</h3><p>${desc}</p></div>
          </div>`).join('')}
      </div>
    </div>
  </section>`;
}

// ─── Profile Page ─────────────────────────────────────────────────────────────
function renderProfilePage() {
  return `
  <div class="container" style="padding:32px 20px 60px">
    <div style="max-width:680px;margin:0 auto">
      <div class="setup-heading">
        <div><span class="eyebrow">STEP 1 OF 1</span><h1 class="section-title">Build your interview profile</h1><p class="section-sub">A few details help Granite tailor the questions to you.</p></div>
        <div class="setup-pill">🎯 10 questions</div>
      </div>

      <div class="card mb-6">
        <div class="card-header"><h2>👤 Personal Details</h2></div>
        <div class="card-body">
          <div class="form-grid">
            <div class="form-group">
              <label>Full Name <span class="req">*</span></label>
              <input type="text" id="inp-name" placeholder="Alex Johnson" autocomplete="name"/>
            </div>
            <div class="form-group">
              <label>Current Role</label>
              <input type="text" id="inp-current-role" placeholder="Software Engineer at Acme"/>
            </div>
          </div>
          <div class="form-grid">
            <div class="form-group">
              <label>Target Role <span class="req">*</span></label>
              <input type="text" id="inp-target-role" placeholder="Senior Software Engineer"/>
            </div>
            <div class="form-group">
              <label>Years of Experience <span class="req">*</span></label>
              <input type="number" id="inp-years" min="0" max="40" placeholder="5"/>
            </div>
          </div>
          <div class="form-grid">
            <div class="form-group">
              <label>Experience Level <span class="req">*</span></label>
              <select id="inp-level">
                <option value="">Select level…</option>
                <option value="junior">Junior (0–2 yrs)</option>
                <option value="mid">Mid-Level (3–5 yrs)</option>
                <option value="senior">Senior (5–8 yrs)</option>
                <option value="lead">Lead / Staff (8+ yrs)</option>
              </select>
            </div>
            <div class="form-group">
              <label>Education</label>
              <input type="text" id="inp-education" placeholder="B.S. Computer Science, MIT"/>
            </div>
          </div>
        </div>
      </div>

      <div class="card mb-6">
        <div class="card-header"><h2>💡 Skills</h2></div>
        <div class="card-body">
          <div class="form-group">
            <label>Technical Skills — press <kbd>Enter</kbd> or <kbd>,</kbd> to add</label>
            <div class="skills-container" id="skills-container">
              <input type="text" class="skills-input" id="skill-input" placeholder="e.g. Python, React, AWS…"/>
            </div>
            <p class="form-hint">Add at least one skill</p>
          </div>
        </div>
      </div>

      <div class="card mb-6">
        <div class="card-header"><h2>📄 Resume <span class="card-header-optional">Optional</span></h2></div>
        <div class="card-body">
          <div class="form-group">
            <label>Upload Resume (PDF or TXT)</label>
            <div class="file-upload-area" id="file-upload-area">
              <input type="file" id="inp-resume" accept=".pdf,.txt"/>
              <div class="file-upload-label">
                <span class="file-upload-icon">📎</span>
                <span id="file-upload-text">Click to choose a file, or drag and drop</span>
              </div>
            </div>
            <div id="resume-status"></div>
          </div>
        </div>
      </div>

      <div class="card mb-6">
        <div class="card-header"><h2>🎙 Interview Focus</h2></div>
        <div class="card-body">
          <p class="text-muted text-sm" style="margin-bottom:14px">Choose the question mix for your session</p>
          <div class="interview-types" id="interview-types">
            ${[
              ['mixed',        '🔀','Mixed',        'All types rotated'],
              ['technical',    '💻','Technical',    'Algorithms, design, code'],
              ['behavioral',   '🗣','Behavioural',  'STAR stories, culture'],
              ['role-specific','🎯','Role-Specific','Domain & responsibilities']
            ].map(([val,icon,label,sub]) => `
              <div class="type-card${val==='mixed'?' selected':''}" data-type="${val}">
                <div class="type-icon">${icon}</div>
                <h3>${label}</h3>
                <p>${sub}</p>
              </div>`).join('')}
          </div>
        </div>
      </div>

      <div class="form-actions">
        <button class="btn btn-secondary" onclick="navigate('home')">← Back</button>
        <button class="btn btn-primary btn-lg" id="start-btn" onclick="startInterview()">
          Start Interview →
        </button>
      </div>
    </div>
  </div>`;
}

// ─── Profile Events ───────────────────────────────────────────────────────────
const skills = [];

function bindProfileEvents() {
  const skillInput = document.getElementById('skill-input');
  if (!skillInput) return;

  skillInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      addSkill(skillInput.value.trim().replace(/,$/, ''));
    }
    if (e.key === 'Backspace' && !skillInput.value && skills.length > 0) {
      removeSkill(skills[skills.length - 1]);
    }
  });
  skillInput.addEventListener('blur', () => {
    if (skillInput.value.trim()) addSkill(skillInput.value.trim());
  });

  document.querySelectorAll('.type-card').forEach(card => {
    card.addEventListener('click', () => {
      document.querySelectorAll('.type-card').forEach(c => c.classList.remove('selected'));
      card.classList.add('selected');
      state.interviewType = card.dataset.type;
    });
  });

  const resumeInput = document.getElementById('inp-resume');
  if (resumeInput) {
    resumeInput.addEventListener('change', async e => {
      const file = e.target.files[0];
      if (!file) return;
      const status = document.getElementById('resume-status');
      const fileText = document.getElementById('file-upload-text');
      status.innerHTML = '<span class="status-info">Parsing resume…</span>';
      try {
        const { resume_text } = await api.uploadResume(file);
        state.resumeText = resume_text;
        if (fileText) fileText.textContent = file.name;
        status.innerHTML = `<span class="status-success">✓ Resume parsed (${resume_text.length} chars)</span>`;
      } catch (err) {
        status.innerHTML = `<span class="status-error">✗ Parse failed: ${err.message}</span>`;
      }
    });
  }
}

function addSkill(val) {
  if (!val || skills.includes(val)) return;
  skills.push(val);
  renderSkillTags();
  document.getElementById('skill-input').value = '';
}

function removeSkill(val) {
  const idx = skills.indexOf(val);
  if (idx > -1) skills.splice(idx, 1);
  renderSkillTags();
}

function renderSkillTags() {
  const container = document.getElementById('skills-container');
  const input = document.getElementById('skill-input');
  Array.from(container.children).forEach(c => { if (c !== input) c.remove(); });
  skills.forEach(s => {
    const tag = document.createElement('span');
    tag.className = 'skill-tag';
    tag.innerHTML = `${escHtml(s)} <button type="button" onclick="removeSkill('${escHtml(s)}')">×</button>`;
    container.insertBefore(tag, input);
  });
}

function startNewSession() {
  state.sessionId = null;
  state.profile = null;
  state.currentQuestion = null;
  state.questionHistory = [];
  state.questionIndex = 0;
  state.skippedQuestionIds = new Set();
  state.answeredQuestionIds = new Set();
  state.completedCount = 0;
  state.currentEvaluation = null;
  state.interviewComplete = false;
  state._nextInFlight = false;
  state.resumeText = '';
  skills.splice(0, skills.length);
  state.interviewType = 'mixed';
  renderApp();
  navigate('profile');
}

// ─── Start Interview ──────────────────────────────────────────────────────────
async function startInterview() {
  const name       = document.getElementById('inp-name')?.value?.trim();
  const targetRole = document.getElementById('inp-target-role')?.value?.trim();
  const level      = document.getElementById('inp-level')?.value;
  const years      = parseInt(document.getElementById('inp-years')?.value || '0');

  if (!name)       return showToast('Please enter your name', 'error');
  if (!targetRole) return showToast('Please enter your target role', 'error');
  if (!level)      return showToast('Please select your experience level', 'error');
  if (!skills.length) return showToast('Please add at least one skill', 'error');

  const btn = document.getElementById('start-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="btn-spinner"></span> Setting up…';

  const profile = {
    name,
    target_role: targetRole,
    experience_level: level,
    years_experience: years,
    current_role: document.getElementById('inp-current-role')?.value?.trim() || '',
    education:    document.getElementById('inp-education')?.value?.trim() || '',
    skills: [...skills],
    resume_text: state.resumeText || ''
  };

  try {
    const session = await api.createSession(profile, state.interviewType);
    // Reset session state
    state.sessionId       = session.session_id;
    state.profile         = profile;
    state.currentQuestion = session.first_question;
    state.questionHistory = [session.first_question];
    state.questionIndex = 0;
    state.skippedQuestionIds = new Set();
    state.answeredQuestionIds = new Set();
    state.completedCount  = 0;
    state.currentEvaluation = null;
    state.interviewComplete = false;
    state._nextInFlight   = false;

    renderInterviewPage();
    navigate('interview');
    showToast('Session started — good luck! 🎯', 'success');
  } catch (e) {
    showToast('Failed to start session: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Start Interview →';
  }
}

// ─── Interview Page ───────────────────────────────────────────────────────────
function renderInterviewPage() {
  const q = state.currentQuestion;
  if (!q || !state.profile) return;
  const qNum = Math.min(state.questionIndex + 1, MAX_QUESTIONS);
  const done = Math.min(state.completedCount, MAX_QUESTIONS);
  const pct = Math.round((done / MAX_QUESTIONS) * 100);
  const isLast = qNum === MAX_QUESTIONS;
  const isSkipped = state.skippedQuestionIds.has(q.id);
  const isAnswered = state.answeredQuestionIds.has(q.id);
  const previousSkippedIndex = state.questionHistory
    .map((item, idx) => ({item, idx}))
    .filter(({item, idx}) => idx < state.questionIndex && state.skippedQuestionIds.has(item.id))
    .map(({idx}) => idx)
    .pop();
  const categoryLabel = (q.category || 'general').replace('-', ' ');

  document.getElementById('page-interview').innerHTML = `
  <div class="interview-shell">
    <div class="interview-topbar container-wide">
      <div class="session-heading"><span class="live-dot"></span><div><strong>Live mock interview</strong><span>${escHtml(state.interviewType)} · ${escHtml(state.profile.target_role)}</span></div></div>
      <div class="top-progress"><span>${done} / ${MAX_QUESTIONS} complete</span><div class="top-progress-track"><div style="width:${pct}%"></div></div></div>
    </div>

    <div class="interview-layout">
      <aside class="interview-sidebar">
        <div class="card sidebar-profile-card">
          <div class="sidebar-avatar">${escHtml(state.profile.name.charAt(0).toUpperCase())}</div>
          <div class="sidebar-name">${escHtml(state.profile.name)}</div>
          <div class="sidebar-role">${escHtml(state.profile.experience_level)} · ${escHtml(state.profile.target_role)}</div>
          <div class="sidebar-type-badge">${escHtml(categoryLabel)}</div>
        </div>

        <div class="card progress-card">
          <div class="card-body">
            <div class="progress-header"><span class="progress-label">Session progress</span><strong class="progress-fraction">${done}/${MAX_QUESTIONS}</strong></div>
            <div class="progress-track"><div class="progress-fill" style="width:${pct}%"></div></div>
            <div class="progress-steps">${Array.from({length:MAX_QUESTIONS},(_,i)=>`<div class="progress-step ${i<done?'step-done':i===qNum-1?'step-current':'step-todo'}" title="Question ${i+1}"></div>`).join('')}</div>
            <div class="progress-caption">${isLast ? 'Final question' : `${MAX_QUESTIONS - done} questions remaining`}</div>
          </div>
        </div>

        <div class="card history-card">
          <div class="card-header"><h2>Question history</h2><span>${state.questionHistory.length}</span></div>
          <div class="card-body" style="padding:8px">
            <div class="q-history">${state.questionHistory.map((q2,i)=>{
              const isCurrent=i===state.questionIndex;
              const skipped=state.skippedQuestionIds.has(q2.id);
              const answered=state.answeredQuestionIds.has(q2.id);
              const clickable=skipped && !isCurrent;
              return `<button type="button" class="q-history-item ${isCurrent?'current':answered?'answered':skipped?'skipped':''} ${clickable?'clickable':''}" ${clickable?`onclick="openQuestion(${i})"`:''}><span class="q-history-num">${answered?'✓':skipped?'↩':'Q'+(i+1)}</span><span class="q-history-text">${escHtml(q2.text.substring(0,54))}${q2.text.length>54?'…':''}</span></button>`;
            }).join('')}</div>
          </div>
        </div>

        <div class="sidebar-actions">
          <button class="btn btn-secondary btn-sm btn-block" onclick="showRecommendations()">💡 Prep Tips</button>
          <button class="btn btn-secondary btn-sm btn-block" onclick="showSummary()">📊 Session Summary</button>
          <button class="btn btn-ghost btn-sm btn-block" onclick="startNewSession()">↺ New Session</button>
        </div>
      </aside>

      <main class="interview-main">
        <div class="question-header">
          <div class="question-meta"><span class="q-badge">${isLast?'🏁 Final Question':'Question '+qNum+' of '+MAX_QUESTIONS}</span><span class="q-category-pill ${escHtml(q.category||'general')}">${escHtml(categoryLabel)}</span>${q.context_used?'<span class="rag-pill">✦ RAG grounded</span>':''}</div>
        </div>

        <div class="question-navigation">
          ${previousSkippedIndex !== undefined ? `<button class="btn btn-secondary btn-sm" onclick="openQuestion(${previousSkippedIndex})">← Return to Q${previousSkippedIndex + 1}</button>` : '<span></span>'}
          ${state.questionIndex > 0 ? `<button class="btn btn-ghost btn-sm" onclick="goToNextVisibleQuestion()">Current / Next →</button>` : ''}
        </div>
        <div class="question-card card">
          <div class="question-card-top"><span>INTERVIEWER</span><span>${isSkipped ? 'Skipped — you can still attempt this' : isAnswered ? 'Answer submitted' : 'Take your time'}</span></div>
          <div class="card-body"><p class="question-text">${escHtml(q.text)}</p></div>
        </div>

        <div id="evaluation-area"></div>

        <div class="card answer-card" id="answer-card">
          <div class="card-header"><div><h2>Your answer</h2><p class="answer-hint">Think aloud, be specific, and support your claims with examples.</p></div><span id="char-count" class="char-count">0 characters</span></div>
          <div class="card-body">
            ${isAnswered ? `<div class="submitted-state"><div class="submitted-icon">✓</div><div><strong>Answer submitted</strong><p>This question is complete. Use the navigation above to continue.</p></div></div>` : `<textarea class="answer-textarea" id="answer-input" placeholder="${isSkipped ? 'You skipped this earlier — you can answer it now…' : 'Start typing your answer…'}

Tip: For behavioural questions, use Situation → Task → Action → Result. For technical questions, explain your reasoning and trade-offs." oninput="updateCharCount(this)"></textarea>
            <div class="answer-footer"><span class="answer-guidance">⌁ Clear answer · concrete evidence · measurable outcome</span><div class="answer-actions"><button class="btn btn-primary" id="submit-btn" onclick="submitAnswer()">${isSkipped ? 'Submit Answer' : 'Submit Answer'} <span>→</span></button>${isSkipped ? '' : '<button class="btn btn-ghost" id="skip-btn" onclick="skipQuestion()">Skip for now</button>'}</div></div>`}
          </div>
        </div>
      </main>
    </div>
  </div>`;
}

function updateCharCount(el) {
  const cnt = document.getElementById('char-count');
  if (cnt) cnt.textContent = `${el.value.length} character${el.value.length !== 1 ? 's' : ''}`;
}

// ─── Submit Answer ────────────────────────────────────────────────────────────
async function submitAnswer() {
  if (state.interviewComplete && !state.skippedQuestionIds.has(state.currentQuestion?.id)) return;
  const answer = document.getElementById('answer-input')?.value?.trim();
  if (!answer || answer.length < 5) return showToast('Please write a more complete answer', 'error');

  const submitBtn = document.getElementById('submit-btn');
  const skipBtn   = document.getElementById('skip-btn');
  submitBtn.disabled = true;
  skipBtn.disabled   = true;
  submitBtn.innerHTML = '<span class="btn-spinner"></span> Evaluating…';

  document.getElementById('evaluation-area').innerHTML = `
    <div class="card eval-loading-card">
      <div class="eval-loading">
        <div class="eval-loading-icon">🤖</div>
        <div class="eval-loading-text">IBM Granite is evaluating your answer…</div>
        <div class="eval-loading-sub">Retrieving knowledge base context and generating feedback</div>
        <div class="loading-dots"><span></span><span></span><span></span></div>
      </div>
    </div>`;

  try {
    const evaluation = await api.evaluateAnswer(state.sessionId, state.currentQuestion.id, answer);
    state.currentEvaluation = evaluation;
    const wasSkipped = state.skippedQuestionIds.has(state.currentQuestion.id);
    if (wasSkipped) state.skippedQuestionIds.delete(state.currentQuestion.id);
    state.answeredQuestionIds.add(state.currentQuestion.id);
    state.completedCount = Number.isFinite(evaluation.questions_completed) ? evaluation.questions_completed : state.completedCount + (wasSkipped ? 0 : 1);
    if (evaluation.is_complete) state.interviewComplete = true;
    renderEvaluation(evaluation, answer);
  } catch (e) {
    showToast('Evaluation failed: ' + e.message, 'error');
    document.getElementById('evaluation-area').innerHTML = '';
    submitBtn.disabled = false;
    skipBtn.disabled   = false;
    submitBtn.textContent = 'Submit Answer';
  }
}

// ─── Render Evaluation ────────────────────────────────────────────────────────
function renderEvaluation(ev, answer) {
  const score      = typeof ev.score === 'number' ? ev.score : 0;
  const scoreClass = score >= 8 ? 'score-high' : score >= 5 ? 'score-mid' : 'score-low';
  const scoreLabel = score >= 8 ? 'Strong' : score >= 5 ? 'Developing' : 'Needs Work';
  const isComplete = state.completedCount >= MAX_QUESTIONS;

  const liItems = arr => (arr || []).map(s => `<li>${escHtml(s)}</li>`).join('');
  const conceptTag = (c, type) => `<span class="concept-tag ${type}">${escHtml(c)}</span>`;
  const covered  = (ev.key_concepts_covered || []).map(c => conceptTag(c, 'covered')).join('');
  const missing  = (ev.key_concepts_missing || []).map(c => conceptTag(c, 'missing')).join('');

  // Safely escape the answer for inline onclick attr (used for follow-up)
  const safeAnswer = answer.substring(0, 400).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/\n/g, ' ');

  document.getElementById('evaluation-area').innerHTML = `
  <div class="card eval-card">
    <div class="eval-header">
      <div class="eval-score-block ${scoreClass}">
        <div class="eval-score-number">${score}</div>
        <div class="eval-score-denom">/10</div>
        <div class="eval-score-label">${scoreLabel}</div>
      </div>
      <div class="eval-summary">
        <div class="eval-summary-title">Overall Assessment</div>
        <p class="eval-summary-text">${escHtml(ev.overall_assessment || '')}</p>
        <div class="eval-badges">
          ${ev.technical_accuracy ? `<span class="eval-badge">${escHtml(ev.technical_accuracy)}</span>` : ''}
          ${ev.communication_quality ? `<span class="eval-badge">${escHtml(ev.communication_quality)}</span>` : ''}
        </div>
      </div>
    </div>

    ${covered || missing ? `
    <div class="eval-concepts">
      <div class="eval-section-label">Key Concepts</div>
      <div class="concept-tags">${covered}${missing}</div>
    </div>` : ''}

    <div class="rubric-grid">
      ${[['relevance','Relevance'],['accuracy','Accuracy'],['completeness','Completeness'],['specificity','Specificity'],['communication','Communication']].map(([key,label])=>{const v=Math.max(0,Math.min(10,Number(ev[key]||0)));return `<div class="rubric-item"><div><span>${label}</span><strong>${v}/10</strong></div><div class="rubric-track"><div style="width:${v*10}%"></div></div></div>`;}).join('')}
    </div>

    <div class="eval-sections">
      <div class="eval-section eval-strengths">
        <div class="eval-section-header">
          <span class="eval-section-icon">✅</span>
          <span class="eval-section-title">Strengths</span>
        </div>
        <ul>${liItems(ev.strengths) || '<li>Keep building on your foundational approach.</li>'}</ul>
      </div>

      <div class="eval-section eval-improvements">
        <div class="eval-section-header">
          <span class="eval-section-icon">⚡</span>
          <span class="eval-section-title">Areas to Improve</span>
        </div>
        <ul>${liItems(ev.improvements) || '<li>Continue practising with more specific examples.</li>'}</ul>
      </div>

      ${(ev.tips || []).length ? `
      <div class="eval-section eval-tips">
        <div class="eval-section-header">
          <span class="eval-section-icon">💡</span>
          <span class="eval-section-title">Tips</span>
        </div>
        <ul>${liItems(ev.tips)}</ul>
      </div>` : ''}

      ${ev.model_answer ? `
      <div class="eval-section eval-model">
        <div class="eval-section-header">
          <span class="eval-section-icon">🎯</span>
          <span class="eval-section-title">Model Answer</span>
        </div>
        <p class="model-answer-text">${escHtml(ev.model_answer)}</p>
      </div>` : ''}
    </div>

    <div class="eval-footer">
      ${isComplete
        ? `<button class="btn btn-primary btn-lg" onclick="showSummary()">View Final Summary 🏁</button>
           <button class="btn btn-secondary" onclick="showRecommendations()">📋 Get Prep Plan</button>`
        : `<button class="btn btn-primary" onclick="nextQuestion()">Next Question →</button>
           <button class="btn btn-secondary" onclick="getFollowup('${safeAnswer}')">🔗 Follow-Up</button>
           <button class="btn btn-ghost"     onclick="showRecommendations()">📋 Tips</button>`}
    </div>
  </div>`;

  const answerCard = document.getElementById('answer-card');
  if (answerCard) answerCard.style.display = 'none';

  if (isComplete) {
    state.interviewComplete = true;
    showToast('🏁 Interview complete! Viewing your final summary…', 'success');
  }
}

// ─── Follow-Up ────────────────────────────────────────────────────────────────
async function getFollowup(originalAnswer) {
  if (!state.sessionId || !state.currentQuestion || !state.currentEvaluation) return;
  const feedbackText = [
    ...(state.currentEvaluation.improvements || []),
    ...(state.currentEvaluation.key_concepts_missing || [])
  ].join(', ');

  try {
    showToast('Generating follow-up…', 'info');
    const { followup_question } = await api.getFollowup(
      state.sessionId, state.currentQuestion.id, originalAnswer, feedbackText
    );
    const evalBody = document.querySelector('.eval-card .eval-sections');
    if (evalBody) {
      const box = document.createElement('div');
      box.className = 'followup-box';
      box.innerHTML = `
        <div class="followup-header">🔗 Follow-Up Question</div>
        <p class="followup-text">${escHtml(followup_question)}</p>`;
      evalBody.after(box);
      box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  } catch (e) {
    showToast('Could not generate follow-up: ' + e.message, 'error');
  }
}

// ─── Skip Question ────────────────────────────────────────────────────────────
async function skipQuestion() {
  if (state.interviewComplete || state._nextInFlight) return;
  if (state.completedCount >= MAX_QUESTIONS) {
    showInterviewComplete();
    return;
  }

  state._nextInFlight = true;
  const skipBtn   = document.getElementById('skip-btn');
  const submitBtn = document.getElementById('submit-btn');
  if (skipBtn)   { skipBtn.disabled = true; skipBtn.innerHTML = '<span class="btn-spinner"></span>'; }
  if (submitBtn) { submitBtn.disabled = true; }

  try {
    await api.skipQuestion(state.sessionId, state.currentQuestion.id);
    state.skippedQuestionIds.add(state.currentQuestion.id);
    state.completedCount++;

    if (state.completedCount >= MAX_QUESTIONS) {
      state.interviewComplete = true;
      showInterviewComplete();
      return;
    }
    await _loadNextQuestion();
  } catch (e) {
    showToast('Skip failed: ' + e.message, 'error');
    if (skipBtn)   { skipBtn.disabled = false; skipBtn.textContent = 'Skip →'; }
    if (submitBtn) { submitBtn.disabled = false; }
  } finally {
    state._nextInFlight = false;
  }
}

// ─── Next Question ────────────────────────────────────────────────────────────
async function nextQuestion() {
  if (state.interviewComplete) {
    showSummary();
    return;
  }
  // If we are viewing an earlier generated question, move through the existing
  // queue before asking the backend to generate anything new.
  if (state.questionIndex < state.questionHistory.length - 1) {
    state.questionIndex++;
    state.currentQuestion = state.questionHistory[state.questionIndex];
    state.currentEvaluation = null;
    renderInterviewPage();
    navigate('interview');
    return;
  }
  if (state._nextInFlight) return;
  if (state.completedCount >= MAX_QUESTIONS) {
    showInterviewComplete();
    return;
  }

  state._nextInFlight = true;

  const evalArea = document.getElementById('evaluation-area');
  if (evalArea) evalArea.innerHTML = `
    <div class="card eval-loading-card">
      <div class="eval-loading">
        <div class="eval-loading-icon">✍️</div>
        <div class="eval-loading-text">Generating next question…</div>
        <div class="loading-dots"><span></span><span></span><span></span></div>
      </div>
    </div>`;

  try {
    await _loadNextQuestion();
  } catch (e) {
    showToast('Could not load next question: ' + e.message, 'error');
  } finally {
    state._nextInFlight = false;
  }
}

async function _loadNextQuestion() {
  const { question } = await api.getNextQuestion(state.sessionId);
  state.currentQuestion   = question;
  state.currentEvaluation = null;
  state.questionHistory.push(question);
  state.questionIndex = state.questionHistory.length - 1;
  renderInterviewPage();
  navigate('interview');
}

function openQuestion(index) {
  const q = state.questionHistory[index];
  if (!q || !state.skippedQuestionIds.has(q.id)) return;
  state.questionIndex = index;
  state.currentQuestion = q;
  state.currentEvaluation = null;
  renderInterviewPage();
  navigate('interview');
  showToast(`Back to Q${index + 1} — you can attempt it now.`, 'info');
}

function goToNextVisibleQuestion() {
  if (state.questionIndex < state.questionHistory.length - 1) {
    state.questionIndex++;
    state.currentQuestion = state.questionHistory[state.questionIndex];
    state.currentEvaluation = null;
    renderInterviewPage();
    navigate('interview');
  }
}

function showInterviewComplete() {
  state.interviewComplete = true;
  const skipped = state.questionHistory.filter(q => state.skippedQuestionIds.has(q.id));
  document.getElementById('page-interview').innerHTML = `
  <div class="complete-page">
    <div class="complete-icon">🏁</div>
    <h1>Interview Complete!</h1>
    <p>You completed all ${MAX_QUESTIONS} questions. Skipped questions are not included in the average, and you can still go back and attempt them.</p>
    ${skipped.length ? `<div class="complete-skipped"><strong>Skipped questions available</strong><div class="complete-skipped-list">${skipped.map(q => {
      const idx = state.questionHistory.findIndex(x => x.id === q.id);
      return `<button class="btn btn-secondary btn-sm" onclick="openQuestion(${idx})">↩ Attempt Q${idx + 1}</button>`;
    }).join('')}</div></div>` : ''}
    <div class="complete-actions">
      <button class="btn btn-primary btn-lg" onclick="showSummary()">View Summary →</button>
      <button class="btn btn-secondary" onclick="showRecommendations()">📋 Prep Plan</button>
      <button class="btn btn-ghost" onclick="startNewSession()">↺ New Session</button>
    </div>
  </div>`;
}

// ─── Recommendations ──────────────────────────────────────────────────────────
async function showRecommendations() {
  navigate('recommendations');
  document.getElementById('page-recommendations').innerHTML = `
  <div class="recommendations-page">
    <div class="page-header">
      <h1>📋 Preparation Plan</h1>
      <p>Personalised study recommendations based on your session</p>
    </div>
    <div class="eval-loading-card card"><div class="eval-loading">
      <div class="eval-loading-icon">🧠</div>
      <div class="eval-loading-text">Analysing your performance…</div>
      <div class="loading-dots"><span></span><span></span><span></span></div>
    </div></div>
  </div>`;

  if (!state.sessionId) {
    document.getElementById('page-recommendations').innerHTML = `
    <div class="recommendations-page">
      <div class="page-header"><h1>📋 Preparation Plan</h1><p>Start a session first.</p></div>
      <button class="btn btn-primary mt-4" onclick="navigate('profile')">Start Session →</button>
    </div>`;
    return;
  }

  try {
    const { recommendations } = await api.getRecommendations(state.sessionId);
    renderRecommendationsPage(recommendations);
  } catch (e) {
    showToast('Could not load recommendations: ' + e.message, 'error');
  }
}

function renderRecommendationsPage(recs) {
  const cards = (recs || []).map(r => `
  <div class="rec-card">
    <div class="rec-top">
      <div class="rec-area">${escHtml(r.area || 'General')}</div>
      <span class="rec-priority ${(r.priority||'medium').toLowerCase()}">${(r.priority||'Medium').toUpperCase()}</span>
    </div>
    <p class="rec-body">${escHtml(r.recommendation || '')}</p>
    <div class="rec-footer">
      ${r.timeline ? `<span class="rec-timeline">⏱ ${escHtml(r.timeline)}</span>` : ''}
      ${(r.resources||[]).map(res => `<span class="rec-resource">${escHtml(res)}</span>`).join('')}
    </div>
  </div>`).join('');

  document.getElementById('page-recommendations').innerHTML = `
  <div class="recommendations-page">
    <div class="page-header">
      <h1>📋 Preparation Plan</h1>
      <p>Personalised study recommendations based on your performance</p>
    </div>
    <div class="page-actions">
      <button class="btn btn-secondary" onclick="navigate('interview')">← Back</button>
      <button class="btn btn-primary"   onclick="showSummary()">📊 Summary</button>
    </div>
    ${cards || '<p class="text-muted">Complete some questions first.</p>'}
  </div>`;
}

// ─── Summary ──────────────────────────────────────────────────────────────────
async function showSummary() {
  navigate('summary');
  document.getElementById('page-summary').innerHTML = `
  <div class="summary-page">
    <div class="eval-loading-card card"><div class="eval-loading">
      <div class="eval-loading-icon">📊</div>
      <div class="eval-loading-text">Building your summary…</div>
      <div class="loading-dots"><span></span><span></span><span></span></div>
    </div></div>
  </div>`;

  if (!state.sessionId) {
    document.getElementById('page-summary').innerHTML = `
    <div class="summary-page">
      <div class="page-header"><h1>Session Summary</h1><p>No active session.</p></div>
      <button class="btn btn-primary mt-4" onclick="navigate('profile')">Start Session →</button>
    </div>`;
    return;
  }

  try {
    const summary = await api.getSummary(state.sessionId);
    renderSummaryPage(summary);
  } catch (e) {
    showToast('Could not load summary: ' + e.message, 'error');
  }
}

function renderSummaryPage(s) {
  const avg = Number(s.average_score || 0);
  const scoreClass = avg >= 8 ? 'score-high' : avg >= 5 ? 'score-mid' : 'score-low';
  const scoreLabel = avg >= 8 ? 'Excellent' : avg >= 6 ? 'Strong progress' : avg >= 4 ? 'Developing' : 'Keep practising';
  const liItems = arr => (arr || []).map(x => `<li>${escHtml(x)}</li>`).join('');
  const categoryEntries = Object.entries(s.category_scores || {});

  document.getElementById('page-summary').innerHTML = `
  <div class="summary-page">
    <div class="summary-hero">
      <div><span class="eyebrow">SESSION COMPLETE</span><h1>Great work, ${escHtml(s.profile?.name || 'Candidate')}.</h1><p>${s.questions_answered || 0}/${s.max_questions || MAX_QUESTIONS} questions completed · ${s.questions_skipped || 0} skipped · ${escHtml(s.interview_type || 'mixed')} practice</p></div>
      <div class="summary-trophy">🏆</div>
    </div>

    <div class="summary-score-card ${scoreClass}">
      <div class="summary-score-num">${avg > 0 ? avg : '—'}</div>
      <div class="summary-score-right"><div class="summary-score-label">${scoreLabel}</div><div class="summary-score-sub">Average score across answered questions</div><div class="summary-score-bar"><div class="summary-score-fill" style="width:${Math.min(100,avg*10)}%"></div></div></div>
    </div>

    <div class="summary-stats">
      <div class="stat-card"><span>Questions</span><strong>${s.questions_answered || 0}</strong><small>completed</small></div>
      <div class="stat-card"><span>Skipped</span><strong>${s.questions_skipped || 0}</strong><small>not included in average</small></div>
      <div class="stat-card"><span>Categories</span><strong>${categoryEntries.length}</strong><small>areas practised</small></div>
    </div>

    ${categoryEntries.length ? `<div class="card category-card"><div class="card-header"><div><h2>Performance by category</h2><p>See where your answers were strongest.</p></div></div><div class="category-list">${categoryEntries.map(([cat,val])=>`<div class="category-row"><div><span>${escHtml(cat.replace('-',' '))}</span><strong>${val}/10</strong></div><div class="category-track"><div style="width:${Math.min(100,val*10)}%"></div></div></div>`).join('')}</div></div>` : ''}

    <div class="summary-grid">
      ${s.top_strengths?.length ? `<div class="card summary-insight strength-card"><div class="card-header"><h2>✓ What you did well</h2></div><div class="card-body"><ul class="summary-list">${liItems(s.top_strengths)}</ul></div></div>` : ''}
      ${s.top_improvements?.length ? `<div class="card summary-insight improvement-card"><div class="card-header"><h2>↗ What to improve next</h2></div><div class="card-body"><ul class="summary-list">${liItems(s.top_improvements)}</ul></div></div>` : ''}
    </div>

    <div class="summary-actions"><button class="btn btn-primary btn-lg" onclick="showRecommendations()">📋 Build My Prep Plan</button><button class="btn btn-secondary" onclick="navigate('interview')">Review Session</button><button class="btn btn-ghost" onclick="startNewSession()">Start New Session</button></div>
  </div>`;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function escHtml(str) {
  if (typeof str !== 'string') return String(str || '');
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function showToast(msg, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = msg;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.35s';
    setTimeout(() => toast.remove(), 380);
  }, 4200);
}
