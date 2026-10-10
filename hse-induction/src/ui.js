const el = (id) => document.getElementById(id);

export function setLoading(fraction) {
  const box = el('loading');
  if (fraction === null) { box.hidden = true; return; }
  box.hidden = false;
  const known = Number.isFinite(fraction);
  el('loading-bar').style.width = known ? `${Math.round(fraction * 100)}%` : '100%';
  el('loading-bar').classList.toggle('indeterminate', !known);
  el('loading-text').textContent = known ? `Loading site… ${Math.round(fraction * 100)}%` : 'Loading site…';
}

export function showError(message, { retry } = {}) {
  setLoading(null);
  el('error-text').textContent = message;
  const btn = el('error-retry');
  btn.hidden = !retry;
  btn.onclick = retry ? () => { el('error').hidden = true; retry(); } : null;
  el('error').hidden = false;
}

let toastTimer;
export function toast(message) {
  const box = el('toast');
  box.textContent = message;
  box.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { box.hidden = true; }, 1500);
}

export function showCard(hotspot) {
  el('card-title').textContent = hotspot.title;
  el('card-points').replaceChildren(...hotspot.points.map((p) => Object.assign(document.createElement('li'), { textContent: p })));
  el('card').hidden = false;
}

export function hideCard() {
  el('card').hidden = true;
}

// items: [{ title, found }]
export function renderChecklist(found, total, items) {
  el('checklist-count').textContent = total ? `${found} of ${total} found` : 'No hotspots yet';
  el('checklist-items').replaceChildren(...items.map((it) => {
    const li = document.createElement('li');
    li.textContent = it.title;
    li.className = it.found ? 'found' : '';
    return li;
  }));
  el('checklist').hidden = false;
}

export function showDone(onClose) {
  document.exitPointerLock?.();
  el('done').hidden = false;
  el('done-close').onclick = () => { el('done').hidden = true; onClose?.(); };
}
