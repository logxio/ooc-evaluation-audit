/* One tooltip for every subpage: an element's aria-description shows in the design-system .tip on hover or focus.
   Window.Tip lets a chart show its own reading in the same layer. */
(() => {
  'use strict';
  const tip = document.createElement('div');
  tip.className = 'tip'; tip.setAttribute('role', 'tooltip');
  let owner = null;
  function place(x, y) {
    const r = tip.getBoundingClientRect();
    let left = Math.min(x + 12, innerWidth - r.width - 8), top = y + 18;
    if (top + r.height > innerHeight - 8) top = y - r.height - 12;
    tip.style.left = Math.max(8, left) + 'px'; tip.style.top = Math.max(8, top) + 'px';
  }
  function show(x, y, text, el) {
    if (!tip.isConnected) document.body.appendChild(tip);
    owner = el || null; tip.textContent = text; tip.classList.add('on'); place(x, y);
  }
  function hide() { owner = null; tip.classList.remove('on'); }
  const host = t => t instanceof Element ? t.closest('[aria-description]') : null;
  document.addEventListener('pointerover', e => {
    const el = host(e.target);
    if (el && el !== owner) show(e.clientX, e.clientY, el.getAttribute('aria-description'), el);
    else if (!el && owner) hide();
  });
  document.addEventListener('pointermove', e => { if (owner) place(e.clientX, e.clientY); });
  document.addEventListener('pointerout', e => { if (!e.relatedTarget) hide(); });
  document.addEventListener('focusin', e => {
    const el = host(e.target);
    if (!el) return;
    const r = el.getBoundingClientRect();
    show(r.left, r.bottom - 6, el.getAttribute('aria-description'), el);
  });
  document.addEventListener('focusout', hide);
  addEventListener('scroll', hide, true);
  window.Tip = { show, hide, place };
})();
