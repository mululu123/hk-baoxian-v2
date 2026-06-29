// Supabase cloud sync — anonymous device-id, last-write-wins per paper.
//
// Schema (run in Supabase SQL editor, see README):
//   user_progress(id, device_id, user_id?, paper_key, progress jsonb, updated_at,
//                 unique(device_id, paper_key))
//
// API:
//   Sync.init(url, anonKey) → bool  (false if config missing or supabase-js absent)
//   Sync.pull()  → Promise<{paperKey: {progress, updated_at}}>  or null on error
//   Sync.push(progressByPaper)      (debounced upsert of all papers)
//   Sync.getStatus()                ('disabled' | 'idle' | 'syncing' | 'error')
//   Sync.getDeviceId()
//
// Emits 'syncstatus' CustomEvent on window whenever state changes.

window.Sync = (function () {
  const DEVICE_ID_KEY = 'iiqe-device-id';
  const PUSH_DEBOUNCE_MS = 1500;

  let client = null;
  let enabled = false;
  let pushTimer = null;
  const state = { status: 'disabled', lastSync: null, error: null };

  function genDeviceId() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    // Fallback for very old browsers
    return 'd_' + Math.random().toString(36).slice(2) + Date.now().toString(36);
  }

  function getDeviceId() {
    let id = localStorage.getItem(DEVICE_ID_KEY);
    if (!id) {
      id = genDeviceId();
      localStorage.setItem(DEVICE_ID_KEY, id);
    }
    return id;
  }

  function emit() {
    window.dispatchEvent(new CustomEvent('syncstatus', { detail: { ...state } }));
  }

  function setStatus(s, error) {
    state.status = s;
    if (error != null) state.error = String(error.message || error);
    else if (s === 'idle' || s === 'syncing') state.error = null;
    if (s === 'idle') state.lastSync = new Date().toISOString();
    emit();
  }

  function init(url, anonKey) {
    if (!url || !anonKey || /^YOUR_/.test(url) || /^YOUR_/.test(anonKey)) {
      setStatus('disabled');
      return false;
    }
    if (!window.supabase || typeof window.supabase.createClient !== 'function') {
      console.warn('[sync] supabase-js not loaded — sync disabled');
      setStatus('error', 'supabase-js not loaded');
      return false;
    }
    client = window.supabase.createClient(url, anonKey, {
      auth: { persistSession: false, autoRefreshToken: false },
    });
    enabled = true;
    setStatus('idle');
    return true;
  }

  async function pull() {
    if (!enabled) return null;
    setStatus('syncing');
    try {
      const { data, error } = await client
        .from('user_progress')
        .select('paper_key, progress, updated_at')
        .eq('device_id', getDeviceId());
      if (error) throw error;
      const map = {};
      (data || []).forEach((row) => {
        map[row.paper_key] = { progress: row.progress, updated_at: row.updated_at };
      });
      setStatus('idle');
      return map;
    } catch (e) {
      setStatus('error', e);
      return null;
    }
  }

  function push(progressByPaper) {
    if (!enabled) return;
    clearTimeout(pushTimer);
    pushTimer = setTimeout(async () => {
      const rows = Object.entries(progressByPaper || {}).map(([paper_key, progress]) => ({
        device_id: getDeviceId(),
        paper_key,
        progress,
      }));
      if (!rows.length) { setStatus('idle'); return; }
      setStatus('syncing');
      try {
        const { error } = await client
          .from('user_progress')
          .upsert(rows, { onConflict: 'device_id,paper_key' });
        if (error) throw error;
        setStatus('idle');
      } catch (e) {
        setStatus('error', e);
      }
    }, PUSH_DEBOUNCE_MS);
  }

  async function clear() {
    if (!enabled) return false;
    setStatus('syncing');
    try {
      const { error } = await client
        .from('user_progress')
        .delete()
        .eq('device_id', getDeviceId());
      if (error) throw error;
      setStatus('idle');
      return true;
    } catch (e) {
      setStatus('error', e);
      return false;
    }
  }

  // ----- Question reports (众包核对) -----
  // Submits a single report. Returns {ok, error?}.
  async function submitReport(report) {
    if (!enabled) return { ok: false, error: 'sync-disabled' };
    setStatus('syncing');
    try {
      const row = {
        device_id: getDeviceId(),
        paper_key: report.paperKey,
        question_id: report.questionId,
        question_no: report.questionNo || null,
        reason: report.reason,
        note: report.note || null,
        suggested_answer: report.suggestedAnswer || null,
      };
      const { error } = await client.from('question_reports').insert(row);
      if (error) throw error;
      setStatus('idle');
      return { ok: true };
    } catch (e) {
      setStatus('error', e);
      return { ok: false, error: String(e.message || e) };
    }
  }

  return {
    init,
    pull,
    push,
    clear,
    submitReport,
    getStatus: () => ({ ...state }),
    getDeviceId,
    isEnabled: () => enabled,
  };
})();
