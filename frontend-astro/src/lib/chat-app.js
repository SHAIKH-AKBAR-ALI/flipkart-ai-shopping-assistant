import { postChat, getSession, deleteSession, ApiError } from './api.js';
import { getSessionId, resetSessionId } from './session.js';
import { loadHistory, saveHistory, clearHistory } from './history.js';

const BOOKING_STEPS = ['collecting_details', 'validating', 'processing_payment', 'creating_order', 'confirmed'];

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str ?? '';
  return div.innerHTML;
}

function formatPrice(value) {
  if (value === null || value === undefined) return '—';
  return `Rs. ${Number(value).toLocaleString('en-IN')}`;
}

function agentBadgeClasses(agent) {
  switch (agent) {
    case 'Sales Agent':
      return 'bg-coral-soft text-coral-dark';
    case 'Technical Agent':
      return 'bg-sage/15 text-sage';
    case 'Booking Agent':
      return 'bg-ink/10 text-ink';
    default:
      return 'bg-ink/10 text-ink-soft';
  }
}

function productCardHtml(product) {
  const rating = product.rating != null ? `★ ${Number(product.rating).toFixed(1)}` : '';
  return `
    <div class="rounded-xl border border-border-soft bg-paper p-4 shadow-sm">
      <p class="font-display text-base text-ink leading-snug">${escapeHtml(product.product_name)}</p>
      <p class="mt-1 text-xs uppercase tracking-wide text-ink-soft">${escapeHtml(product.brand || '')} ${product.category ? '· ' + escapeHtml(product.category) : ''}</p>
      <div class="mt-3 flex items-center justify-between">
        <span class="font-display text-lg text-coral-dark">${formatPrice(product.price)}</span>
        ${rating ? `<span class="text-sm text-ink-soft">${rating}</span>` : ''}
      </div>
    </div>
  `;
}

function bookingProgressHtml(bookingState) {
  const step = bookingState.step;
  const failed = step === 'failed';
  const stepIndex = failed ? BOOKING_STEPS.length : BOOKING_STEPS.indexOf(step);
  const labels = ['Details', 'Validating', 'Payment', 'Order', 'Confirmed'];

  const dots = labels
    .map((label, i) => {
      const done = i < stepIndex || (i === stepIndex && step === 'confirmed');
      const active = i === stepIndex && step !== 'confirmed';
      const dotClass = failed && i === stepIndex
        ? 'bg-red-400 text-white'
        : done
          ? 'bg-coral text-white'
          : active
            ? 'bg-coral-soft text-coral-dark border border-coral'
            : 'bg-ink/10 text-ink-soft';
      return `
        <div class="flex flex-1 flex-col items-center gap-1">
          <div class="flex h-6 w-6 items-center justify-center rounded-full text-xs font-medium ${dotClass}">${i + 1}</div>
          <span class="text-[11px] text-ink-soft">${label}</span>
        </div>
      `;
    })
    .join('<div class="mt-3 h-px flex-1 bg-border-soft"></div>');

  if (step === 'confirmed' && bookingState.order) {
    const order = bookingState.order;
    return `
      <div class="rounded-xl border border-coral/40 bg-coral-soft/40 p-5">
        <div class="mb-4 flex items-center">${dots}</div>
        <p class="font-display text-lg text-coral-dark">Order confirmed</p>
        <dl class="mt-3 space-y-1 text-sm text-ink">
          <div class="flex justify-between"><dt class="text-ink-soft">Order ID</dt><dd class="font-mono">${escapeHtml(order.order_id)}</dd></div>
          <div class="flex justify-between"><dt class="text-ink-soft">Product</dt><dd>${escapeHtml(order.product_name)}</dd></div>
          <div class="flex justify-between"><dt class="text-ink-soft">Price</dt><dd>${formatPrice(order.price)}</dd></div>
        </dl>
      </div>
    `;
  }

  if (failed) {
    return `
      <div class="rounded-xl border border-red-200 bg-red-50 p-5">
        <div class="mb-4 flex items-center">${dots}</div>
        <p class="font-display text-lg text-red-700">Booking failed</p>
        <p class="mt-1 text-sm text-red-600">${escapeHtml(bookingState.error || 'Unknown error')}</p>
      </div>
    `;
  }

  const showForm = step === 'collecting_details';
  return `
    <div class="rounded-xl border border-border-soft bg-paper p-5">
      <div class="mb-4 flex items-center">${dots}</div>
      ${showForm ? bookingFormHtml(bookingState) : '<p class="text-sm text-ink-soft">Working on it…</p>'}
    </div>
  `;
}

function bookingFormHtml(bookingState) {
  const details = bookingState.details || {};
  return `
    <form data-booking-form class="space-y-3">
      <div>
        <label class="mb-1 block text-xs font-medium text-ink-soft">Name</label>
        <input name="name" value="${escapeHtml(details.name || '')}" class="w-full rounded-lg border border-border-soft bg-cream px-3 py-2 text-sm focus:border-coral focus:outline-none" placeholder="Rahul Sharma" />
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-ink-soft">Address</label>
        <input name="address" value="${escapeHtml(details.address || '')}" class="w-full rounded-lg border border-border-soft bg-cream px-3 py-2 text-sm focus:border-coral focus:outline-none" placeholder="221B MG Road, Mumbai" />
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-ink-soft">Payment method</label>
        <input name="payment" value="${escapeHtml(details.payment_method || '')}" class="w-full rounded-lg border border-border-soft bg-cream px-3 py-2 text-sm focus:border-coral focus:outline-none" placeholder="UPI" />
      </div>
      <button type="submit" class="w-full rounded-lg bg-coral px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-coral-dark">
        Continue booking
      </button>
    </form>
  `;
}

export function initChatApp({ categoryLabel, seedMessage }) {
  const els = {
    messages: document.getElementById('chat-messages'),
    form: document.getElementById('chat-form'),
    input: document.getElementById('chat-input'),
    sendBtn: document.getElementById('chat-send'),
    newConvoBtn: document.getElementById('new-conversation'),
    errorBanner: document.getElementById('error-banner'),
    errorText: document.getElementById('error-text'),
    retryBtn: document.getElementById('error-retry'),
    typing: document.getElementById('typing-indicator'),
  };

  let sessionId = getSessionId();
  let history = loadHistory(sessionId);
  let lastFailedMessage = null;

  function render() {
    els.messages.innerHTML = history
      .map((msg) => {
        if (msg.role === 'user') {
          return `
            <div class="flex justify-end">
              <div class="max-w-[80%] rounded-2xl rounded-br-sm bg-coral px-4 py-3 text-white">
                <p class="text-sm leading-relaxed">${escapeHtml(msg.content)}</p>
              </div>
            </div>
          `;
        }

        const badge = msg.agent_used
          ? `<span class="mb-2 inline-block rounded-full px-2.5 py-0.5 text-[11px] font-medium uppercase tracking-wide ${agentBadgeClasses(msg.agent_used)}">${escapeHtml(msg.agent_used)}</span>`
          : '';
        const products =
          msg.retrieved_products && msg.retrieved_products.length
            ? `<div class="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">${msg.retrieved_products.map(productCardHtml).join('')}</div>`
            : '';
        const booking = msg.booking_state ? `<div class="mt-3">${bookingProgressHtml(msg.booking_state)}</div>` : '';

        return `
          <div class="flex justify-start">
            <div class="max-w-[85%] rounded-2xl rounded-bl-sm border border-border-soft bg-paper px-4 py-3">
              ${badge}
              <p class="text-sm leading-relaxed text-ink whitespace-pre-wrap">${escapeHtml(msg.content)}</p>
              ${products}
              ${booking}
            </div>
          </div>
        `;
      })
      .join('');

    const bookingForm = els.messages.querySelector('[data-booking-form]');
    if (bookingForm) {
      bookingForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const data = new FormData(bookingForm);
        const parts = [];
        if (data.get('name')) parts.push(`name: ${data.get('name')}`);
        if (data.get('address')) parts.push(`address: ${data.get('address')}`);
        if (data.get('payment')) parts.push(`payment: ${data.get('payment')}`);
        if (parts.length) sendMessage(parts.join(', '));
      });
    }

    els.messages.scrollTop = els.messages.scrollHeight;
    saveHistory(sessionId, history);
  }

  function setLoading(loading) {
    els.sendBtn.disabled = loading;
    els.input.disabled = loading;
    els.typing.classList.toggle('hidden', !loading);
  }

  function showError(message) {
    els.errorText.textContent = message;
    els.errorBanner.classList.remove('hidden');
  }

  function hideError() {
    els.errorBanner.classList.add('hidden');
  }

  async function sendMessage(text) {
    const trimmed = text.trim();
    if (!trimmed) return;

    hideError();
    history.push({ role: 'user', content: trimmed });
    render();
    setLoading(true);

    try {
      const res = await postChat(sessionId, trimmed);

      // /chat doesn't return booking_state directly — fetch the session
      // snapshot so booking progress/confirmation renders on this turn.
      let bookingState = null;
      if (res.intent === 'booking') {
        try {
          const session = await getSession(sessionId);
          bookingState = session.booking_state || null;
        } catch {
          // non-fatal — message still renders without booking UI
        }
      }

      history.push({
        role: 'assistant',
        content: res.message,
        agent_used: res.agent_used,
        retrieved_products: res.retrieved_products,
        booking_state: bookingState,
      });
      render();
      lastFailedMessage = null;
    } catch (err) {
      history.pop(); // roll back the optimistic user bubble's pairing so retry re-sends cleanly
      history.push({ role: 'user', content: trimmed });
      lastFailedMessage = trimmed;
      if (err instanceof ApiError && err.status === 503) {
        showError('Backend is still starting up. Retry in about a minute.');
      } else if (err instanceof ApiError) {
        showError(`Something went wrong: ${err.message}`);
      } else {
        showError('Could not reach the server. Check your connection and retry.');
      }
      render();
    } finally {
      setLoading(false);
    }
  }

  els.form.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = els.input.value;
    els.input.value = '';
    sendMessage(text);
  });

  els.retryBtn.addEventListener('click', () => {
    if (lastFailedMessage) {
      const msg = lastFailedMessage;
      history.pop();
      hideError();
      sendMessage(msg);
    }
  });

  els.newConvoBtn.addEventListener('click', async () => {
    try {
      await deleteSession(sessionId);
    } catch {
      // best-effort — clear client state regardless
    }
    clearHistory(sessionId);
    sessionId = resetSessionId();
    history = [];
    hideError();
    render();
    sendMessage(seedMessage);
  });

  render();

  if (history.length === 0) {
    sendMessage(seedMessage);
  }
}
