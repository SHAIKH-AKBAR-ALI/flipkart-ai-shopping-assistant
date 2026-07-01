// Backend GET /session only returns a message_count + state snapshot, not the
// rendered transcript, so we keep a client-side copy of message bubbles to
// restore the UI on refresh. Namespaced per session_id.
function key(sessionId) {
  return `flipkart_history_${sessionId}`;
}

export function loadHistory(sessionId) {
  try {
    return JSON.parse(sessionStorage.getItem(key(sessionId)) || '[]');
  } catch {
    return [];
  }
}

export function saveHistory(sessionId, history) {
  sessionStorage.setItem(key(sessionId), JSON.stringify(history));
}

export function clearHistory(sessionId) {
  sessionStorage.removeItem(key(sessionId));
}
