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

// Sales/Technical bubbles double as the retrieval source indicator — Booking
// Agent and Supervisor don't retrieve products, so they never get a suffix.
function agentSourceSuffix(agentUsed, products) {
  if (agentUsed !== 'Sales Agent' && agentUsed !== 'Technical Agent') return '';
  if (!products || !products.length) return '';
  const isLive = products.some((p) => p.web_source);
  return isLive ? ' · \u{1F310} Live' : ' · \u{1F5C4}\u{FE0F} DB';
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

const _STAR_SVG =
  '<svg viewBox="0 0 20 20" fill="currentColor" class="inline-block h-3.5 w-3.5 text-coral align-[-2px]"><path d="M10 1.5l2.59 5.25 5.79.84-4.19 4.09.99 5.77L10 14.77l-5.18 2.68.99-5.77L1.62 7.59l5.79-.84L10 1.5z"/></svg>';

// Products only carry a free-text `content`/`specifications` blob (no dedicated
// "Details" field in the RAG schema) — pull the "Specifications: ..." tail out of
// it and split on the delimiters the catalog actually uses (pipe, plus comma/semicolon
// as a fallback for categories that format it differently).
function parseDetailBullets(product) {
  if (product.specifications && typeof product.specifications === 'object') {
    const entries = Object.entries(product.specifications);
    if (entries.length) return entries.map(([k, v]) => `${k}: ${v}`);
  }
  const text = product.content || product.details || product.summary || '';
  const match = text.match(/Specifications:\s*(.+)/is);
  const raw = match ? match[1] : text;
  return raw
    .split(/[|,;]/)
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, 8);
}

function productCardHtml(product, checked) {
  const ratingHtml =
    product.rating != null
      ? `<span class="flex items-center gap-1 text-sm font-semibold text-ink">${_STAR_SVG}${Number(product.rating).toFixed(1)}</span>`
      : '';
  const priceHtml =
    product.web_source && !product.price
      ? `<span class="font-display text-sm italic text-ink-soft opacity-70">Price unavailable</span>`
      : `<span class="font-display text-xl text-coral-dark">${formatPrice(product.price)}</span>`;
  const webBadgeHtml = product.web_source
    ? `<span data-web-source-badge class="absolute left-2 top-2 z-10 rounded-full border border-border-soft bg-cream/90 px-1.5 py-0.5 text-[10px] font-medium leading-none text-ink-soft opacity-80">🌐 Live data</span>`
    : '';
  return `
    <div data-product-card data-product-id="${escapeHtml(product.product_id)}" class="group relative cursor-pointer rounded-xl border border-border-soft border-l-4 border-l-coral bg-paper p-4 shadow-sm transition-all duration-150 hover:-translate-y-0.5 hover:shadow-md">
      ${webBadgeHtml}
      <label data-compare-checkbox-wrap class="absolute right-2 top-2 z-10 flex items-center rounded-full bg-paper/90 p-1 opacity-100 shadow-sm transition-opacity sm:opacity-0 sm:group-hover:opacity-100">
        <input type="checkbox" data-compare-checkbox data-product-id="${escapeHtml(product.product_id)}" ${checked ? 'checked' : ''} class="h-3.5 w-3.5 accent-coral" aria-label="Select for compare" />
      </label>
      <p class="pr-6 font-display text-base font-semibold leading-snug text-ink">${escapeHtml(product.product_name)}</p>
      <p class="mt-1 text-xs uppercase tracking-wide text-ink-soft opacity-60">${escapeHtml(product.brand || '')} ${product.category ? '· ' + escapeHtml(product.category) : ''}</p>
      <div class="mt-3 flex items-center justify-between">
        ${priceHtml}
        ${ratingHtml}
      </div>
    </div>
  `;
}

function compareTableHtml(products) {
  const prices = products.map((p) => p.price).filter((v) => v != null);
  const minPrice = prices.length ? Math.min(...prices) : null;
  const ratings = products.map((p) => (p.rating != null ? Number(p.rating) : null)).filter((v) => v != null);
  const maxRating = ratings.length ? Math.max(...ratings) : null;

  const specsByProduct = products.map((p) => parseDetailBullets(p).slice(0, 3));
  const specRowCount = Math.max(0, ...specsByProduct.map((s) => s.length));

  const headerCells = products
    .map((p) => `<th class="px-3 py-2 text-left font-display text-sm text-ink">${escapeHtml(p.product_name)}</th>`)
    .join('');

  const priceRow = `
    <tr class="border-t border-border-soft">
      <td class="px-3 py-2 text-xs font-medium uppercase tracking-wide text-ink-soft">Price</td>
      ${products
        .map(
          (p) =>
            `<td class="px-3 py-2 text-sm ${p.price === minPrice ? 'font-semibold text-sage' : 'text-ink'}">${formatPrice(p.price)}</td>`
        )
        .join('')}
    </tr>
  `;

  const ratingRow = `
    <tr class="border-t border-border-soft">
      <td class="px-3 py-2 text-xs font-medium uppercase tracking-wide text-ink-soft">Rating</td>
      ${products
        .map((p) => {
          const r = p.rating != null ? Number(p.rating) : null;
          const best = r != null && maxRating != null && r === maxRating;
          return `<td class="px-3 py-2 text-sm ${best ? 'font-semibold text-sage' : 'text-ink'}">${r != null ? r.toFixed(1) : '—'}</td>`;
        })
        .join('')}
    </tr>
  `;

  let specRows = '';
  for (let i = 0; i < specRowCount; i++) {
    specRows += `
      <tr class="border-t border-border-soft">
        <td class="px-3 py-2 text-xs font-medium uppercase tracking-wide text-ink-soft">Spec ${i + 1}</td>
        ${specsByProduct.map((specs) => `<td class="px-3 py-2 text-xs text-ink-soft">${escapeHtml(specs[i] || '—')}</td>`).join('')}
      </tr>
    `;
  }

  return `
    <div class="mb-3 overflow-x-auto rounded-xl border border-border-soft">
      <table class="w-full border-collapse">
        <thead class="bg-cream"><tr><th class="px-3 py-2"></th>${headerCells}</tr></thead>
        <tbody>${priceRow}${ratingRow}${specRows}</tbody>
      </table>
    </div>
  `;
}

// Highest rating wins; ties broken by lower price.
function pickWinner(products) {
  return products.reduce((best, p) => {
    if (!best) return p;
    const pRating = p.rating != null ? Number(p.rating) : -Infinity;
    const bestRating = best.rating != null ? Number(best.rating) : -Infinity;
    if (pRating > bestRating) return p;
    if (pRating === bestRating && (p.price ?? Infinity) < (best.price ?? Infinity)) return p;
    return best;
  }, null);
}

function recommendationBannerHtml(products) {
  const winner = pickWinner(products);
  if (!winner) return '';
  return `
    <div data-recommendation class="mb-3 rounded-xl border border-coral/30 bg-coral-soft/40 p-4">
      <p class="text-sm text-ink">
        ${_STAR_SVG} We recommend <span class="font-semibold">${escapeHtml(winner.product_name)}</span> —
        highest rated at ${winner.rating != null ? Number(winner.rating).toFixed(1) : '—'}, priced at ${formatPrice(winner.price)}
      </p>
      <div class="mt-3 flex gap-2">
        <button type="button" data-recommend-book data-product-name="${escapeHtml(winner.product_name)}" class="rounded-lg bg-coral px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-coral-dark">
          Book recommended
        </button>
        <button type="button" data-recommend-other class="rounded-lg border border-coral px-4 py-2 text-sm font-medium text-coral-dark transition-colors hover:bg-coral-soft">
          Book a different one
        </button>
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

// Exact text of the Supervisor's first-turn clarification (backend/agents/supervisor.py
// clarify_msg) — matched verbatim so we can swap it for a budget quick-pick UI client-side.
const _CLARIFY_TEXT =
  "I want to make sure I get this right — are you asking about pricing/offers, specs/comparisons, or ready to book something?";

function budgetRangesFor(categoryLabel) {
  const noun = categoryLabel.toLowerCase();

  if (categoryLabel === 'Laptops') {
    return [
      { label: 'Under ₹30k', message: `show me ${noun} under 30000` },
      { label: '₹30k–50k', message: `show me ${noun} from 30000 to 50000` },
      { label: '₹50k–70k', message: `show me ${noun} from 50000 to 70000` },
      { label: '₹70k–1L', message: `show me ${noun} from 70000 to 100000` },
      { label: 'Above ₹1L', message: `show me ${noun} above 100000` },
    ];
  }
  if (categoryLabel === 'TVs') {
    return [
      { label: 'Under ₹15k', message: `show me ${noun} under 15000` },
      { label: '₹15k–30k', message: `show me ${noun} from 15000 to 30000` },
      { label: '₹30k–50k', message: `show me ${noun} from 30000 to 50000` },
      { label: '₹50k–80k', message: `show me ${noun} from 50000 to 80000` },
      { label: 'Above ₹80k', message: `show me ${noun} above 80000` },
    ];
  }
  if (categoryLabel === 'Refrigerators' || categoryLabel === 'Washing Machines') {
    return [
      { label: 'Under ₹15k', message: `show me ${noun} under 15000` },
      { label: '₹15k–25k', message: `show me ${noun} from 15000 to 25000` },
      { label: '₹25k–40k', message: `show me ${noun} from 25000 to 40000` },
      { label: 'Above ₹40k', message: `show me ${noun} above 40000` },
    ];
  }
  // Mobiles / Smart Watches (default)
  return [
    { label: 'Under ₹10k', message: `show me ${noun} under 10000` },
    { label: '₹10k–20k', message: `show me ${noun} from 10000 to 20000` },
    { label: '₹20k–35k', message: `show me ${noun} from 20000 to 35000` },
    { label: '₹35k–50k', message: `show me ${noun} from 35000 to 50000` },
    { label: 'Above ₹50k', message: `show me ${noun} above 50000` },
  ];
}

function budgetPickerHtml(categoryLabel) {
  const buttons = budgetRangesFor(categoryLabel)
    .map(
      (r) =>
        `<button type="button" data-budget-option data-message="${escapeHtml(r.message)}" class="rounded-full border border-coral px-4 py-1.5 text-sm font-medium text-coral-dark transition-colors hover:bg-coral-soft">${escapeHtml(r.label)}</button>`
    )
    .join('');
  return `
    <div data-budget-picker>
      <p class="text-sm leading-relaxed text-ink">What's your budget?</p>
      <div class="mt-3 flex flex-wrap gap-2">${buttons}</div>
    </div>
  `;
}

const _PAYMENT_METHODS = ['UPI', 'Credit Card', 'Net Banking'];

function bookingFormHtml(bookingState) {
  const details = bookingState.details || {};
  const paymentButtons = _PAYMENT_METHODS
    .map((method) => {
      const selected = details.payment_method === method;
      const cls = selected
        ? 'border-coral bg-coral-soft text-coral-dark'
        : 'border-border-soft bg-cream text-ink-soft';
      return `<button type="button" data-payment-option data-value="${method}" class="payment-btn rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${cls}">${method}</button>`;
    })
    .join('');

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
        <label class="mb-1 block text-xs font-medium text-ink-soft">Phone Number</label>
        <input name="phone" value="${escapeHtml(details.phone || '')}" class="w-full rounded-lg border border-border-soft bg-cream px-3 py-2 text-sm focus:border-coral focus:outline-none" placeholder="9876543210" />
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-ink-soft">Payment method</label>
        <input type="hidden" name="payment" value="${escapeHtml(details.payment_method || '')}" />
        <div class="grid grid-cols-3 gap-2" data-payment-buttons>${paymentButtons}</div>
      </div>
      <button type="submit" data-continue-btn disabled class="w-full rounded-lg bg-coral px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-coral-dark disabled:cursor-not-allowed disabled:opacity-50">
        Continue booking
      </button>
    </form>
  `;
}

export function initChatApp({ categoryLabel, categorySlug, seedMessage }) {
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
    compareBar: document.getElementById('compare-bar'),
    compareBtn: document.getElementById('compare-btn'),
    detailOverlay: document.getElementById('product-detail-overlay'),
    detailPanel: document.getElementById('product-detail-panel'),
    detailContent: document.getElementById('detail-content'),
    detailCloseBtn: document.getElementById('detail-close-btn'),
  };

  let sessionId = getSessionId();
  let history = loadHistory(sessionId);
  let lastFailedMessage = null;
  let compareSelection = []; // product_ids selected for compare, max 3 — reset on new conversation
  let productIndex = new Map(); // product_id -> product, rebuilt every render() from history

  function updateCompareBar() {
    const n = compareSelection.length;
    els.compareBar.classList.toggle('hidden', n === 0);
    els.compareBtn.textContent = `Compare (${n})`;
    els.compareBtn.disabled = n < 2;
  }

  function showCompareTooltip(wrapEl) {
    const tip = document.createElement('div');
    tip.textContent = 'Max 3 products';
    tip.className =
      'absolute right-0 top-[-1.75rem] z-20 whitespace-nowrap rounded-md bg-ink px-2 py-1 text-[11px] text-white shadow-md';
    wrapEl.appendChild(tip);
    setTimeout(() => tip.remove(), 1500);
  }

  function closeDetailPanel() {
    els.detailPanel.classList.add('translate-x-full');
    els.detailOverlay.classList.add('hidden');
  }

  function openDetailPanel(product) {
    const bullets = parseDetailBullets(product);
    const hasMrp = product.mrp != null && product.mrp > product.price;
    const mrpHtml = hasMrp
      ? `<p class="mt-1 text-sm text-ink-soft"><span class="line-through">${formatPrice(product.mrp)}</span>${
          product.discount ? ` <span class="ml-2 font-medium text-sage">${escapeHtml(String(product.discount))}</span>` : ''
        }</p>`
      : '';

    els.detailContent.innerHTML = `
      <p class="text-xs uppercase tracking-wide text-ink-soft opacity-60">${escapeHtml(product.brand || '')}${
        product.category ? ' · ' + escapeHtml(product.category) : ''
      }</p>
      <h2 class="mt-1 font-display text-2xl leading-snug text-ink">${escapeHtml(product.product_name)}</h2>
      <div class="mt-3 flex items-center gap-3">
        <span class="font-display text-2xl text-coral-dark">${formatPrice(product.price)}</span>
        ${
          product.rating != null
            ? `<span class="flex items-center gap-1 text-sm font-semibold text-ink">${_STAR_SVG}${Number(product.rating).toFixed(1)}</span>`
            : ''
        }
      </div>
      ${mrpHtml}
      ${
        bullets.length
          ? `<ul class="mt-5 space-y-2 text-sm text-ink">${bullets
              .map((b) => `<li class="flex gap-2"><span class="text-coral">•</span><span>${escapeHtml(b)}</span></li>`)
              .join('')}</ul>`
          : ''
      }
      <div class="mt-8 space-y-2">
        <button type="button" data-detail-ask class="w-full rounded-lg border border-coral px-4 py-2 text-sm font-medium text-coral-dark transition-colors hover:bg-coral-soft">
          Ask about this
        </button>
        <button type="button" data-detail-compare class="w-full rounded-lg border border-border-soft px-4 py-2 text-sm font-medium text-ink transition-colors hover:border-coral">
          Compare
        </button>
        <button type="button" data-detail-book class="w-full rounded-lg bg-coral px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-coral-dark">
          Book this
        </button>
      </div>
    `;

    els.detailPanel.classList.remove('translate-x-full');
    els.detailOverlay.classList.remove('hidden');

    els.detailContent.querySelector('[data-detail-ask]').addEventListener('click', () => {
      closeDetailPanel();
      els.input.value = `${product.product_name} — `;
      els.input.focus();
    });
    els.detailContent.querySelector('[data-detail-compare]').addEventListener('click', () => {
      addToCompare(product.product_id);
      closeDetailPanel();
    });
    els.detailContent.querySelector('[data-detail-book]').addEventListener('click', () => {
      closeDetailPanel();
      sendMessage(`I want to book ${product.product_name}`);
    });
  }

  function addToCompare(productId) {
    if (compareSelection.includes(productId)) return;
    if (compareSelection.length >= 3) return;
    compareSelection.push(productId);
    updateCompareBar();
    render();
  }

  els.detailCloseBtn.addEventListener('click', closeDetailPanel);
  els.detailOverlay.addEventListener('click', closeDetailPanel);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeDetailPanel();
  });

  els.compareBtn.addEventListener('click', () => {
    if (compareSelection.length < 2) return;
    const products = compareSelection.map((id) => productIndex.get(id)).filter(Boolean);
    if (products.length < 2) return;
    const message = `Compare these products: ${products.map((p) => p.product_name).join(' vs ')}`;
    sendMessage(message, { compare_products: products });
  });

  function render() {
    productIndex = new Map();
    history.forEach((msg) => {
      (msg.retrieved_products || []).forEach((p) => productIndex.set(p.product_id, p));
      (msg.compare_products || []).forEach((p) => productIndex.set(p.product_id, p));
    });

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

        if (msg.content === _CLARIFY_TEXT) {
          return `
            <div class="flex justify-start">
              <div class="max-w-[85%] rounded-2xl rounded-bl-sm border border-border-soft bg-paper px-4 py-3">
                ${budgetPickerHtml(categoryLabel)}
              </div>
            </div>
          `;
        }

        const badge = msg.agent_used
          ? `<span class="mb-2 inline-block rounded-full px-2.5 py-0.5 text-[11px] font-medium uppercase tracking-wide ${agentBadgeClasses(msg.agent_used)}">${escapeHtml(msg.agent_used)}${agentSourceSuffix(msg.agent_used, msg.retrieved_products)}</span>`
          : '';
        const products =
          msg.retrieved_products && msg.retrieved_products.length
            ? `<div class="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">${msg.retrieved_products
                .map((p) => productCardHtml(p, compareSelection.includes(p.product_id)))
                .join('')}</div>`
            : '';
        const booking = msg.booking_state ? `<div class="mt-3">${bookingProgressHtml(msg.booking_state)}</div>` : '';
        const compareHtml =
          msg.compare_products && msg.compare_products.length >= 2
            ? compareTableHtml(msg.compare_products) + recommendationBannerHtml(msg.compare_products)
            : '';
        const bubbleWidth = compareHtml ? 'max-w-[95%]' : 'max-w-[85%]';

        return `
          <div class="flex justify-start">
            <div class="${bubbleWidth} rounded-2xl rounded-bl-sm border border-border-soft bg-paper px-4 py-3">
              ${compareHtml}
              ${badge}
              <p class="text-sm leading-relaxed text-ink whitespace-pre-wrap">${escapeHtml(msg.content)}</p>
              ${products}
              ${booking}
            </div>
          </div>
        `;
      })
      .join('');

    els.messages.querySelectorAll('[data-budget-option]').forEach((btn) => {
      btn.addEventListener('click', () => sendMessage(btn.dataset.message));
    });

    els.messages.querySelectorAll('[data-product-card]').forEach((card) => {
      card.addEventListener('click', () => {
        const product = productIndex.get(card.dataset.productId);
        if (product) openDetailPanel(product);
      });
    });

    els.messages.querySelectorAll('[data-compare-checkbox]').forEach((cb) => {
      cb.addEventListener('click', (e) => e.stopPropagation());
      cb.addEventListener('change', () => {
        const id = cb.dataset.productId;
        if (cb.checked) {
          if (compareSelection.length >= 3) {
            cb.checked = false;
            showCompareTooltip(cb.closest('[data-compare-checkbox-wrap]'));
            return;
          }
          compareSelection.push(id);
        } else {
          compareSelection = compareSelection.filter((x) => x !== id);
        }
        updateCompareBar();
        render();
      });
    });

    els.messages.querySelectorAll('[data-recommend-book]').forEach((btn) => {
      btn.addEventListener('click', () => sendMessage(`I want to book ${btn.dataset.productName}`));
    });
    els.messages.querySelectorAll('[data-recommend-other]').forEach((btn) => {
      btn.addEventListener('click', () => {
        compareSelection = [];
        updateCompareBar();
        render();
      });
    });

    const bookingForm = els.messages.querySelector('[data-booking-form]');
    if (bookingForm) {
      const paymentHidden = bookingForm.querySelector('input[name="payment"]');
      const paymentButtons = bookingForm.querySelectorAll('[data-payment-option]');
      const continueBtn = bookingForm.querySelector('[data-continue-btn]');
      const nameInput = bookingForm.querySelector('input[name="name"]');
      const addressInput = bookingForm.querySelector('input[name="address"]');
      const phoneInput = bookingForm.querySelector('input[name="phone"]');

      function highlightSelected() {
        paymentButtons.forEach((btn) => {
          const selected = btn.dataset.value === paymentHidden.value;
          btn.classList.toggle('border-coral', selected);
          btn.classList.toggle('bg-coral-soft', selected);
          btn.classList.toggle('text-coral-dark', selected);
          btn.classList.toggle('border-border-soft', !selected);
          btn.classList.toggle('bg-cream', !selected);
          btn.classList.toggle('text-ink-soft', !selected);
        });
      }

      function updateContinueState() {
        const ready =
          nameInput.value.trim() && addressInput.value.trim() && phoneInput.value.trim() && paymentHidden.value;
        continueBtn.disabled = !ready;
      }

      paymentButtons.forEach((btn) => {
        btn.addEventListener('click', () => {
          paymentHidden.value = btn.dataset.value;
          highlightSelected();
          updateContinueState();
        });
      });
      [nameInput, addressInput, phoneInput].forEach((inp) =>
        inp.addEventListener('input', updateContinueState)
      );

      updateContinueState();

      bookingForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const data = new FormData(bookingForm);
        const parts = [];
        if (data.get('name')) parts.push(`name: ${data.get('name')}`);
        if (data.get('address')) parts.push(`address: ${data.get('address')}`);
        if (data.get('phone')) parts.push(`phone: ${data.get('phone')}`);
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

  async function sendMessage(text, meta = {}) {
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
      let selectedProduct = null;
      if (res.intent === 'booking') {
        try {
          const session = await getSession(sessionId);
          bookingState = session.booking_state || null;
          selectedProduct = session.selected_product || null;
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
        ...meta,
      });

      if (meta.compare_products) {
        compareSelection = [];
        updateCompareBar();
      }

      render();
      lastFailedMessage = null;

      if (bookingState && bookingState.step === 'processing_payment') {
        sessionStorage.setItem(
          'flipkart_payment_context',
          JSON.stringify({
            amount: selectedProduct ? selectedProduct.price : null,
            method: bookingState.details ? bookingState.details.payment_method : null,
            categorySlug,
          })
        );
        window.location.href = '/payment';
        return;
      }
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

  async function reportPaymentResult(success) {
    hideError();
    setLoading(true);
    try {
      const res = await postChat(sessionId, success ? 'payment_confirmed' : 'payment_failed');
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
    } catch {
      showError('Could not confirm payment status with the server.');
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
    compareSelection = [];
    updateCompareBar();
    closeDetailPanel();
    hideError();
    render();
    sendMessage(seedMessage);
  });

  render();

  const params = new URLSearchParams(window.location.search);
  const paymentStatus = params.get('payment');
  if (paymentStatus === 'success' || paymentStatus === 'failed') {
    window.history.replaceState({}, '', window.location.pathname);
    reportPaymentResult(paymentStatus === 'success');
  } else if (history.length === 0) {
    sendMessage(seedMessage);
  }
}
