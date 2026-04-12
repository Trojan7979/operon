const runtimeConfig = window.__APP_CONFIG__ ?? {};
const API_BASE =
  runtimeConfig.VITE_API_BASE_URL ??
  import.meta.env.VITE_API_BASE_URL ??
  'http://127.0.0.1:8000/api/v1';

const SESSION_KEY = 'nexuscore-session';
const TRACE_LIMIT = 25;
const apiTraceListeners = new Set();
const apiTrace = [];

function emitApiTrace(entry) {
  apiTrace.unshift(entry);
  if (apiTrace.length > TRACE_LIMIT) {
    apiTrace.length = TRACE_LIMIT;
  }
  apiTraceListeners.forEach((listener) => listener([...apiTrace]));
}

async function request(path, { method = 'GET', token, body } = {}) {
  const url = `${API_BASE}${path}`;
  const startedAt = Date.now();
  let response;

  try {
    response = await fetch(url, {
      method,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
  } catch (error) {
    emitApiTrace({
      id: `${startedAt}-${path}`,
      method,
      path,
      url,
      status: 'NETWORK_ERROR',
      ok: false,
      durationMs: Date.now() - startedAt,
      createdAt: new Date(startedAt).toISOString(),
      error: error.message || 'Network request failed.',
    });
    throw error;
  }

  emitApiTrace({
    id: `${startedAt}-${path}`,
    method,
    path,
    url,
    status: response.status,
    ok: response.ok,
    durationMs: Date.now() - startedAt,
    createdAt: new Date(startedAt).toISOString(),
  });

  if (!response.ok) {
    let message = 'Request failed.';
    try {
      const errorPayload = await response.json();
      message = errorPayload.detail || message;
    } catch {
      message = response.statusText || message;
    }
    throw new Error(message);
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

export function getApiBase() {
  return API_BASE;
}

export function subscribeApiTrace(listener) {
  apiTraceListeners.add(listener);
  listener([...apiTrace]);
  return () => {
    apiTraceListeners.delete(listener);
  };
}

export function getStoredSession() {
  try {
    const raw = window.localStorage.getItem(SESSION_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function storeSession(session) {
  window.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

export function clearStoredSession() {
  window.localStorage.removeItem(SESSION_KEY);
}

export function login(email, password) {
  return request('/auth/login', {
    method: 'POST',
    body: { email, password },
  });
}

export function fetchCurrentUser(token) {
  return request('/auth/me', { token });
}

export function fetchDashboardOverview(token) {
  return request('/dashboard/overview', { token });
}

export function fetchWorkflows(token) {
  return request('/workflows', { token });
}

export function advanceWorkflow(token, workflowId) {
  return request(`/workflows/${workflowId}/advance`, {
    method: 'POST',
    token,
  });
}

export function fetchMeetings(token) {
  return request('/meetings', { token });
}

export function scheduleMeeting(token, payload) {
  return request('/meetings', {
    method: 'POST',
    token,
    body: payload,
  });
}

export function analyzeMeeting(token, meetingId) {
  return request(`/meetings/${meetingId}/analyze`, {
    method: 'POST',
    token,
  });
}

export function fetchEmployees(token) {
  return request('/employees', { token });
}

export function createEmployee(token, payload) {
  return request('/employees', {
    method: 'POST',
    token,
    body: payload,
  });
}

export function fetchUsers(token) {
  return request('/rbac/users', { token });
}

export function createUser(token, payload) {
  return request('/rbac/users', {
    method: 'POST',
    token,
    body: payload,
  });
}

export function updateUser(token, userId, payload) {
  return request(`/rbac/users/${userId}`, {
    method: 'PATCH',
    token,
    body: payload,
  });
}

export function fetchSlaOverview(token) {
  return request('/sla/overview', { token });
}

export function sendAgentMessage(token, agentId, message, conversationId = null) {
  return request('/chat/message', {
    method: 'POST',
    token,
    body: {
      agentId,
      message,
      ...(conversationId ? { conversationId } : {}),
    },
  });
}
