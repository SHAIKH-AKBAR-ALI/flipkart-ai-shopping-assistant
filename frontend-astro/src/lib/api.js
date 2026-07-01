import { API_BASE_URL } from '../config.js';

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function handle(res) {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // response had no JSON body
    }
    throw new ApiError(typeof detail === 'string' ? detail : JSON.stringify(detail), res.status);
  }
  return res.json();
}

export async function postChat(sessionId, message) {
  const res = await fetch(`${API_BASE_URL}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message }),
  });
  return handle(res);
}

export async function getSession(sessionId) {
  const res = await fetch(`${API_BASE_URL}/session/${sessionId}`);
  return handle(res);
}

export async function deleteSession(sessionId) {
  const res = await fetch(`${API_BASE_URL}/session/${sessionId}`, { method: 'DELETE' });
  return handle(res);
}
