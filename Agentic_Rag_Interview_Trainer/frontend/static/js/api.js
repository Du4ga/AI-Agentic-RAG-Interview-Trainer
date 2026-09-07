/**
 * API Client — communicates with the FastAPI backend
 */
const API_BASE = window.location.port === '5500' || window.location.port === '5501'
  ? 'http://localhost:8000'
  : '';

const api = {
  async request(method, path, body = null) {
    const opts = {
      method,
      headers: { 'Content-Type': 'application/json' }
    };
    if (body) opts.body = JSON.stringify(body);
    const resp = await fetch(`${API_BASE}${path}`, opts);
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }
    return resp.json();
  },

  get: (path) => api.request('GET', path),
  post: (path, body) => api.request('POST', path, body),

  async health() {
    return api.get('/health');
  },

  async initKB() {
    return api.post('/api/kb/initialize', {});
  },

  async createSession(profile, interviewType) {
    return api.post('/api/session/create', {
      profile,
      interview_type: interviewType
    });
  },

  async getSession(sessionId) {
    return api.get(`/api/session/${sessionId}`);
  },

  async evaluateAnswer(sessionId, questionId, answer) {
    return api.post('/api/interview/evaluate', {
      session_id: sessionId,
      question_id: questionId,
      answer
    });
  },

  async getNextQuestion(sessionId) {
    return api.post('/api/interview/next-question', {
      session_id: sessionId
    });
  },

  async skipQuestion(sessionId, questionId) {
    return api.post('/api/interview/skip', {
      session_id: sessionId,
      question_id: questionId
    });
  },

  async getFollowup(sessionId, questionId, originalAnswer, feedbackReceived) {
    return api.post('/api/interview/followup', {
      session_id: sessionId,
      question_id: questionId,
      original_answer: originalAnswer,
      feedback_received: feedbackReceived
    });
  },

  async getRecommendations(sessionId) {
    return api.post('/api/interview/recommendations', {
      session_id: sessionId
    });
  },

  async getSummary(sessionId) {
    return api.get(`/api/interview/summary/${sessionId}`);
  },

  async uploadResume(file) {
    const form = new FormData();
    form.append('file', file);
    const resp = await fetch(`${API_BASE}/api/resume/upload`, { method: 'POST', body: form });
    if (!resp.ok) throw new Error('Resume upload failed');
    return resp.json();
  }
};
