/* One page-local monitor. Only YouTube's visible, enabled Skip Ad controls. */
(function install() {
  if (!/(^|\.)youtube\.com$/.test(location.hostname)) return;
  const previous = window.__orionSkipWatcher;
  if (previous?.version === 3 && !previous.stopped) return;
  previous?.stop?.();

  const selector = '.ytp-ad-skip-button,.ytp-ad-skip-button-modern,' +
    '.ytp-skip-ad-button,.ytp-ad-skip-button-container button';
  const candidates = new Set();
  const states = new WeakMap();
  const pending = new Set();
  const samples = [];
  const counters = {scans: 0, checks: 0, mutations: 0, clicks: 0};
  let observer, timer, stopped = false, lastScan = -Infinity;
  const now = () => performance.now();
  const adPlaying = () => !!document.querySelector('.html5-video-player.ad-showing');
  const eligible = button => {
    if (!button.isConnected || button.disabled || button.matches(':disabled') ||
        button.closest('[aria-disabled="true"],[inert]')) return false;
    const style = getComputedStyle(button);
    if (!button.getClientRects().length || style.visibility !== 'visible' ||
        style.display === 'none' || style.pointerEvents === 'none') return false;
    for (let node = button; node; node = node.parentElement) {
      if (Number(getComputedStyle(node).opacity) === 0) return false;
    }
    return true;
  };
  const add = root => {
    if (!(root instanceof Element)) return;
    if (root.matches(selector)) candidates.add(root);
    if (root.childElementCount) {
      for (const button of root.querySelectorAll(selector)) candidates.add(button);
    }
  };
  const scan = () => {
    counters.scans++;
    lastScan = now();
    for (const button of document.querySelectorAll(selector)) candidates.add(button);
  };
  const confirm = () => {
    for (const sample of pending) {
      const button = sample.button;
      const result = !button.isConnected ? 'control_removed' :
        !eligible(button) ? 'control_unavailable' :
        sample.ad_before && !adPlaying() ? 'ad_ended' : null;
      if (result || now() - sample.clicked_at_ms >= 1000) {
        const state = states.get(button);
        if (state && result) state.handled = true;
        sample.confirmed = !!result;
        sample.confirmation = result || 'not_confirmed';
        sample.confirmation_ms = now() - sample.clicked_at_ms;
        delete sample.button;
        pending.delete(sample);
        console.debug('[ORION][skip]', JSON.stringify(sample));
      }
    }
  };
  const check = (source = 'mutation') => {
    if (stopped) return null;
    confirm();
    let dispatched = null;
    for (const button of candidates) {
      if (!button.isConnected || !button.matches(selector)) {
        candidates.delete(button);
        states.delete(button);
        continue;
      }
      const started = now();
      counters.checks++;
      let state = states.get(button);
      if (!state) {
        state = {first_seen_ms: started, last_click_ms: -Infinity, attempts: 0};
        states.set(button, state);
      }
      if (!eligible(button)) {
        state.handled = false;
        state.attempts = 0;
        state.last_click_ms = -Infinity;
        continue;
      }
      // Per-control backoff prevents spam without delaying a different ad's control.
      if (state.handled || started - state.last_click_ms < 1000 || state.attempts >= 3) continue;
      const detected = now();
      const sample = {source, first_seen_ms: state.first_seen_ms,
        eligible_observed_at_ms: detected, detection_ms: detected - started,
        eligibility_wait_ms: detected - state.first_seen_ms,
        ad_before: adPlaying(), confirmed: false};
      state.last_click_ms = now();
      state.attempts++;
      sample.clicked_at_ms = now();
      sample.dispatch_ms = sample.clicked_at_ms - detected;
      // No seeking, timer changes, request interception, or player API bypass.
      button.click();
      sample.click_handler_ms = now() - sample.clicked_at_ms;
      counters.clicks++;
      sample.button = button;
      samples.push(sample);
      if (samples.length > 100) samples.shift();
      pending.add(sample);
      dispatched = sample;
      break;
    }
    confirm();
    return dispatched;
  };
  const navigation = () => { scan(); check('navigation'); };
  const stop = () => {
    stopped = true;
    observer?.disconnect();
    clearInterval(timer);
    document.removeEventListener('yt-navigate-finish', navigation);
    document.removeEventListener('DOMContentLoaded', start);
    window.removeEventListener('pagehide', suspend);
    candidates.clear();
    for (const sample of pending) delete sample.button;
    pending.clear();
  };
  const suspend = () => {
    stop();
    window.addEventListener('pageshow', event => {
      if (event.persisted) install();
    }, {once: true});
  };
  const monitor = {
    version: 3, get stopped() { return stopped; }, stop,
    tick: () => !!check('driver'),
    skip: () => { scan(); return !!check('manual'); },
    snapshot: (limit = 100) => ({enabled: !stopped, counters: {...counters},
      skip_available: !stopped && Array.from(candidates).some(eligible),
      samples: samples.slice(-Math.max(1, Math.min(100, limit)))
        .map(({button, ...sample}) => ({...sample}))})
  };
  window.__orionSkipWatcher = monitor;
  const start = () => {
    if (stopped || observer) return;
    observer = new MutationObserver(records => {
      counters.mutations += records.length;
      let relevant = false;
      for (const record of records) {
        if (record.type === 'childList') {
          for (const node of record.addedNodes) {
            const count = candidates.size;
            add(node);
            if (candidates.size !== count) relevant = true;
          }
          if (record.removedNodes.length && (pending.size || candidates.size)) relevant = true;
        } else if (record.target instanceof Element) {
          const target = record.target;
          if (target.matches(selector)) { candidates.add(target); relevant = true; }
          for (const button of candidates) {
            if (target === button || target.contains(button)) { relevant = true; break; }
          }
        }
      }
      if (relevant) check('mutation');
    });
    observer.observe(document.documentElement, {childList: true, subtree: true,
      attributes: true, attributeFilter: ['class', 'style', 'disabled', 'aria-disabled', 'hidden', 'inert']});
    scan();
    check('initial');
    // CSS animations and stylesheets can change visibility without a DOM mutation.
    timer = setInterval(() => {
      if (now() - lastScan >= 1000) scan();
      check('fallback');
    }, 50);
    document.addEventListener('yt-navigate-finish', navigation);
    window.addEventListener('pagehide', suspend);
  };
  if (document.documentElement) start();
  else document.addEventListener('DOMContentLoaded', start, {once: true});
})();
