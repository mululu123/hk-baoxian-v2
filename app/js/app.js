'use strict';

// ============ 状态 ============
const State = {
  currentPaper: null,     // 当前选中的题库 key
  currentMode: null,      // 'random' | 'section' | 'sequential' | 'errors'
  queue: [],              // 当前题库的题目数组
  cursor: 0,              // 当前题目在 queue 中的索引
  selectedAnswer: null,   // 当前题已选的答案
  answered: false,        // 当前题是否已答
  // 从 localStorage 加载
  progress: {},           // { paperKey: { sequentialCursor, randomHistory: [...], wrongBook: [...], stats: {answered, correct} } }
};

// ============ 持久化 ============
const STORAGE_KEY = 'iiqe-app-state-v1';

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) State.progress = JSON.parse(raw);
  } catch (e) { console.warn('loadState failed', e); }
  if (!State.progress) State.progress = {};
}
function saveState() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(State.progress));
  } catch (e) { console.warn('saveState failed', e); }
  // Push to cloud (debounced, no-op if sync disabled)
  if (window.Sync) Sync.push(State.progress);
}
function getPaperProgress(paperKey) {
  if (!State.progress[paperKey]) {
    State.progress[paperKey] = {
      sequentialCursor: 0,
      randomHistory: [],   // [{id, qno, question, yourAnswer, correctAnswer, correct, ts}]
      wrongBook: [],       // [question ids]
      stats: { answered: 0, correct: 0 },
      _updatedAt: 0,       // ms epoch, used for last-write-wins cloud merge
    };
  }
  return State.progress[paperKey];
}
function touchPaperProgress(paperKey) {
  const p = getPaperProgress(paperKey);
  p._updatedAt = Date.now();
}

// ============ 工具 ============
const $ = (sel, parent = document) => parent.querySelector(sel);
const $$ = (sel, parent = document) => Array.from(parent.querySelectorAll(sel));

function el(tag, props = {}, ...children) {
  const e = document.createElement(tag);
  Object.entries(props).forEach(([k, v]) => {
    if (v == null) return;
    if (k === 'class') e.className = v;
    else if (k === 'html') e.innerHTML = v;
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'dataset') Object.assign(e.dataset, v);
    else if (typeof v === 'boolean') {
      // Boolean HTML attributes (disabled, hidden, checked, ...): presence = true.
      // setAttribute(k, false) sets the string "false" which is truthy, so we must skip it.
      if (v) e.setAttribute(k, '');
    }
    else e.setAttribute(k, v);
  });
  children.forEach(c => {
    if (c == null || c === false) return;
    if (c instanceof Node) e.appendChild(c);
    else e.appendChild(document.createTextNode(String(c)));
  });
  return e;
}

function shuffle(arr) {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function escapeHTML(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function getBank(paperKey) {
  return window.QUESTION_BANKS[paperKey];
}

// ============ 题库懒加载 ============
// 首屏只载 _meta.js (~3KB)，进入模式时再载具体题库 (~150KB/库)。
// 避免一次性下 4 个文件 1.8MB。
const _bankLoadPromises = {};
function ensureBank(paperKey) {
  if (window.QUESTION_BANKS[paperKey]) {
    return Promise.resolve(window.QUESTION_BANKS[paperKey]);
  }
  if (_bankLoadPromises[paperKey]) return _bankLoadPromises[paperKey];
  _bankLoadPromises[paperKey] = new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = `data/${paperKey}.js`;
    script.onload = () => {
      const bank = window.QUESTION_BANKS[paperKey];
      if (bank) resolve(bank);
      else reject(new Error('題庫資料缺失'));
    };
    script.onerror = () => {
      delete _bankLoadPromises[paperKey];
      reject(new Error('題庫下載失敗，請檢查網路'));
    };
    document.head.appendChild(script);
  });
  return _bankLoadPromises[paperKey];
}

function showLoading(text) {
  let overlay = document.getElementById('loading-overlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'loading-overlay';
    overlay.innerHTML = '<div class="spinner"></div><div class="loading-text"></div>';
    document.body.appendChild(overlay);
  }
  overlay.querySelector('.loading-text').textContent = text || '載入中…';
  overlay.classList.add('show');
}
function hideLoading() {
  const overlay = document.getElementById('loading-overlay');
  if (overlay) overlay.classList.remove('show');
}

// ============ 视图渲染 ============
function showTopbar(show) {
  $('#topbar').hidden = !show;
}
function showBottombar(show) {
  $('#bottombar').hidden = !show;
}
function setTopbar(paperLabel, modeLabel, counter) {
  $('#topbar-paper').textContent = paperLabel || '';
  $('#topbar-mode').textContent = modeLabel || '';
  $('#topbar-counter').textContent = counter || '';
}

// ----- 首页 -----
function renderHome() {
  showTopbar(false);
  showBottombar(false);
  const meta = window.QUESTION_BANKS_META || [];
  const totalAnswered = meta.reduce((sum, m) => {
    const p = State.progress[m.key];
    return sum + (p ? p.stats.answered : 0);
  }, 0);
  const totalCorrect = meta.reduce((sum, m) => {
    const p = State.progress[m.key];
    return sum + (p ? p.stats.correct : 0);
  }, 0);
  const totalWrong = meta.reduce((sum, m) => {
    const p = State.progress[m.key];
    return sum + (p ? p.wrongBook.length : 0);
  }, 0);
  const accuracy = totalAnswered > 0 ? Math.round(totalCorrect * 100 / totalAnswered) : 0;

  const view = $('#view');
  view.innerHTML = '';

  view.appendChild(el('div', { class: 'home-hero' },
    el('h1', {}, 'IIQE 模擬試題刷題'),
    el('p', {}, `共 ${meta.reduce((s, m) => s + m.total, 0)} 題 · 4 份題庫 · 離線可用`),
    renderSyncBadge(),
  ));

  view.appendChild(el('div', { class: 'section-title' }, '① 選擇題庫'));
  const grid = el('div', { class: 'bank-grid' });
  meta.forEach(m => {
    const isSelected = State.currentPaper === m.key;
    const p = State.progress[m.key];
    const card = el('button', {
      class: 'bank-card' + (isSelected ? ' selected' : ''),
      onclick: () => {
        State.currentPaper = State.currentPaper === m.key ? null : m.key;
        renderHome();
      },
    },
      el('span', { class: 'badge' }, m.edition),
      el('h3', {}, m.label),
      el('div', { class: 'subject' }, m.subject),
      el('div', { class: 'count' }, `${m.total} 題 · ${m.sections} 章節`),
    );
    grid.appendChild(card);
  });
  view.appendChild(grid);

  view.appendChild(el('div', { class: 'section-title' }, '② 選擇模式'));
  const modeList = el('div', { class: 'mode-list' });
  const modes = [
    { key: 'random', icon: '🎲', title: '隨機快測', desc: '隨機抽 N 題快速測驗', min: 'paper' },
    { key: 'section', icon: '📑', title: '按章節練習', desc: '挑選特定章節集中練習', min: 'paper' },
    { key: 'sequential', icon: '📚', title: '順序過題', desc: '從頭到尾完整刷一遍，自動記錄進度', min: 'paper' },
    { key: 'errors', icon: '❌', title: '錯題本', desc: '重做答錯的題目', min: 'paper' },
  ];
  modes.forEach(m => {
    const disabled = !State.currentPaper;
    const btn = el('button', {
      class: 'mode-btn',
      disabled,
      onclick: () => enterMode(m.key),
    },
      el('div', { class: 'icon' }, m.icon),
      el('div', { class: 'text' },
        el('div', { class: 'title' }, m.title),
        el('div', { class: 'desc' }, m.desc),
      ),
      el('div', { class: 'arrow' }, '›'),
    );
    if (m.key === 'errors') {
      const p = State.currentPaper ? getPaperProgress(State.currentPaper) : null;
      const wrongCount = p ? p.wrongBook.length : 0;
      btn.querySelector('.desc').textContent = wrongCount > 0
        ? `當前 ${wrongCount} 道錯題待重做`
        : '重做答錯的題目';
      if (State.currentPaper && wrongCount === 0) btn.disabled = true;
    }
    modeList.appendChild(btn);
  });
  view.appendChild(modeList);

  view.appendChild(el('div', { class: 'section-title' }, '③ 整體統計'));
  view.appendChild(el('div', { class: 'stats-row' },
    el('div', { class: 'stat-card' },
      el('div', { class: 'num' }, totalAnswered),
      el('div', { class: 'lbl' }, '已答題數'),
    ),
    el('div', { class: 'stat-card' },
      el('div', { class: 'num success' }, accuracy + '%'),
      el('div', { class: 'lbl' }, '正確率'),
    ),
    el('div', { class: 'stat-card' },
      el('div', { class: 'num danger' }, totalWrong),
      el('div', { class: 'lbl' }, '錯題本'),
    ),
  ));

  // 备份/还原/清除
  const tools = el('div', { class: 'home-tools' },
    el('button', { class: 'ghost', onclick: exportProgress }, '💾 備份'),
    el('button', { class: 'ghost', onclick: importProgress }, '📂 還原'),
  );
  if (totalAnswered > 0) {
    tools.appendChild(el('button', {
      class: 'ghost danger',
      onclick: async () => {
        if (!confirm('確定清除所有學習記錄和錯題本？此操作不可撤銷。')) return;
        localStorage.removeItem(STORAGE_KEY);
        State.progress = {};
        // Also delete cloud copy so next pull doesn't restore it
        if (window.Sync && Sync.isEnabled()) await Sync.clear();
        renderHome();
      },
    }, '🗑️ 清除所有記錄'));
  }
  view.appendChild(tools);
}

// ----- 备份 / 还原 -----
function exportProgress() {
  const payload = {
    app: 'iiqe-mock-exam',
    version: 1,
    exportedAt: new Date().toISOString(),
    progress: State.progress,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  const today = new Date().toISOString().slice(0, 10);
  a.href = url;
  a.download = `iiqe-backup-${today}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function importProgress() {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = 'application/json,.json';
  input.onchange = () => {
    const file = input.files && input.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const data = JSON.parse(reader.result);
        if (!data || data.app !== 'iiqe-mock-exam' || !data.progress) {
          alert('檔案格式不正確，不是本 app 匯出的備份。');
          return;
        }
        const banks = Object.keys(data.progress);
        const summary = banks.map(k => {
          const p = data.progress[k] || {};
          const ans = p.stats && p.stats.answered || 0;
          const wrong = (p.wrongBook || []).length;
          return `  · ${k}: 已答 ${ans} 題, 錯題 ${wrong} 道`;
        }).join('\n');
        const ok = confirm(`將還原以下進度（會覆蓋當前數據）：\n${summary}\n\n繼續？`);
        if (!ok) return;
        State.progress = data.progress;
        saveState();
        renderHome();
        alert('✅ 還原完成');
      } catch (e) {
        alert('解析失敗：' + e.message);
      }
    };
    reader.readAsText(file);
  };
  input.click();
}

// ----- 进入模式 -----
async function enterMode(mode) {
  if (!State.currentPaper) return;
  State.currentMode = mode;
  let bank;
  try {
    showLoading('正在載入題庫…');
    bank = await ensureBank(State.currentPaper);
  } catch (e) {
    alert(e.message || '題庫載入失敗');
    return;
  } finally {
    hideLoading();
  }
  if (!bank) return;

  if (mode === 'random') {
    showRandomSetup(bank);
  } else if (mode === 'section') {
    showSectionList(bank);
  } else if (mode === 'sequential') {
    const p = getPaperProgress(State.currentPaper);
    State.queue = bank.questions.slice();
    State.cursor = p.sequentialCursor < State.queue.length ? p.sequentialCursor : 0;
    startQuiz();
  } else if (mode === 'errors') {
    const p = getPaperProgress(State.currentPaper);
    if (p.wrongBook.length === 0) {
      alert('當前題庫還沒有錯題！');
      return;
    }
    const wrongIds = new Set(p.wrongBook);
    State.queue = bank.questions.filter(q => wrongIds.has(q.id));
    State.cursor = 0;
    startQuiz();
  }
}

// ----- 随机模式设置 -----
function showRandomSetup(bank) {
  showTopbar(true);
  setTopbar(bank.label, '隨機快測', '');
  showBottombar(false);
  const view = $('#view');
  view.innerHTML = '';

  view.appendChild(el('div', { class: 'question-card' },
    el('div', { class: 'q-text', style: 'font-size: 18px;' }, '選擇題數'),
    el('div', { class: 'muted', style: 'font-size: 13px; margin-top: 4px;' }, `題庫共 ${bank.total} 題`),
  ));

  const counts = [10, 20, 30, 50, 100];
  if (bank.total < 100) {
    while (counts[counts.length - 1] > bank.total) counts.pop();
  }
  const settingsRow = el('div', { class: 'settings-row' });
  let selectedCount = 20;
  counts.forEach((c, i) => {
    const chip = el('button', {
      class: 'chip' + (c === selectedCount ? ' selected' : ''),
      onclick: () => {
        selectedCount = c;
        settingsRow.querySelectorAll('.chip').forEach(x => x.classList.remove('selected'));
        chip.classList.add('selected');
      },
    }, c + ' 題');
    settingsRow.appendChild(chip);
  });
  view.appendChild(settingsRow);

  view.appendChild(el('div', { style: 'margin-top: 20px;' },
    el('button', {
      class: 'primary large block',
      onclick: () => {
        const n = Math.min(selectedCount, bank.total);
        State.queue = shuffle(bank.questions).slice(0, n);
        State.cursor = 0;
        startQuiz();
      },
    }, '開始'),
  ));
}

// ----- 章节列表 -----
function showSectionList(bank) {
  showTopbar(true);
  setTopbar(bank.label, '按章節練習', '');
  showBottombar(false);
  const view = $('#view');
  view.innerHTML = '';

  // 用数据文件预计算好的 sections 列表（已归并）
  const sections = bank.sections || [];

  view.appendChild(el('div', { class: 'section-title' }, `共 ${sections.length} 個章節`));
  const list = el('div', { class: 'section-list' });
  sections.forEach(sec => {
    const item = el('div', {
      class: 'section-item',
      onclick: () => {
        // 按 sectionKey 过滤题目
        const key = sec.key;
        const matched = bank.questions.filter(q => q.sectionKey === key);
        State.queue = shuffle(matched);
        State.cursor = 0;
        startQuiz();
      },
    },
      el('span', { class: 'sec-no' }, sec.display),
      el('span', { class: 'sec-count' }, sec.count + ' 題'),
      el('span', { class: 'arrow' }, '›'),
    );
    list.appendChild(item);
  });
  view.appendChild(list);
}

// ----- 开始测验 -----
function startQuiz() {
  const bank = getBank(State.currentPaper);
  const modeLabels = { random: '隨機快測', section: '章節練習', sequential: '順序過題', errors: '錯題本' };
  showTopbar(true);
  showBottombar(true);
  setTopbar(bank.label, modeLabels[State.currentMode] || '', `1 / ${State.queue.length}`);
  State.selectedAnswer = null;
  State.answered = false;
  renderQuestion();
  updateProgress();
}

// ----- 渲染当前题 -----
function renderQuestion() {
  const q = State.queue[State.cursor];
  if (!q) {
    showResult();
    return;
  }
  const bank = getBank(State.currentPaper);
  const modeLabels = { random: '隨機快測', section: '章節練習', sequential: '順序過題', errors: '錯題本' };
  setTopbar(bank.label, modeLabels[State.currentMode], `${State.cursor + 1} / ${State.queue.length}`);
  $('#topbar').querySelector('#btn-exit').onclick = exitQuiz;

  const view = $('#view');
  view.innerHTML = '';

  const card = el('div', { class: 'question-card' });
  const meta = el('div', { class: 'q-meta' });
  meta.appendChild(el('span', { class: 'tag qno' }, q.no || '—'));
  if (q.section) meta.appendChild(el('span', { class: 'tag section' }, '章節 ' + q.section));
  meta.appendChild(el('button', {
    class: 'tag report-btn',
    title: '舉報此題有問題',
    onclick: () => openReportModal(q),
  }, '⚠ 舉報'));
  card.appendChild(meta);

  card.appendChild(el('div', { class: 'q-text' }, q.question));

  const optionsBox = el('div', { class: 'options' });
  ['A', 'B', 'C', 'D'].forEach(letter => {
    const text = q.options[letter];
    if (!text) return;
    const opt = el('button', {
      class: 'option',
      dataset: { letter },
      onclick: () => selectAnswer(letter),
    },
      el('span', { class: 'letter' }, letter),
      el('span', { class: 'content' }, text),
    );
    optionsBox.appendChild(opt);
  });
  card.appendChild(optionsBox);

  // 如果已答，恢复状态
  if (State.answered) {
    showResultOnCard(card, q);
  }

  view.appendChild(card);
  view.scrollTop = 0;
}

function selectAnswer(letter) {
  if (State.answered) return;
  State.selectedAnswer = letter;
  State.answered = true;
  const q = State.queue[State.cursor];

  // 评分
  const correct = letter === q.answer;
  const paperProg = getPaperProgress(State.currentPaper);
  paperProg.stats.answered++;
  if (correct) {
    paperProg.stats.correct++;
    // 答对：从错题本移除（如果在）
    paperProg.wrongBook = paperProg.wrongBook.filter(id => id !== q.id);
  } else {
    // 答错：加入错题本（去重）
    if (!paperProg.wrongBook.includes(q.id)) paperProg.wrongBook.push(q.id);
  }
  // 历史
  if (State.currentMode === 'random') {
    paperProg.randomHistory.push({
      id: q.id, qno: q.no,
      question: q.question.slice(0, 80),
      yourAnswer: letter, correctAnswer: q.answer,
      correct, ts: Date.now(),
    });
    if (paperProg.randomHistory.length > 200) paperProg.randomHistory.shift();
  }
  paperProg._updatedAt = Date.now();
  saveState();

  // 重新渲染（显示答案）
  renderQuestion();
  updateProgress();
}

function showResultOnCard(card, q) {
  // 标记选项
  const opts = $$('.option', card);
  opts.forEach(o => {
    const letter = o.dataset.letter;
    o.classList.add('disabled');
    if (letter === q.answer) {
      o.classList.add('correct');
      o.appendChild(el('span', { class: 'mark' }, '✓'));
    } else if (letter === State.selectedAnswer) {
      o.classList.add('wrong');
      o.appendChild(el('span', { class: 'mark' }, '✗'));
    }
  });

  // 结果 banner
  const correct = State.selectedAnswer === q.answer;
  const banner = el('div', {
    class: 'result-banner ' + (correct ? 'correct' : 'wrong'),
  }, correct ? '✓ 正確' : `✗ 錯誤 · 正確答案是 ${q.answer}`);
  card.appendChild(banner);

  // 解析
  const expl = q.explanation || '';
  const hasRealExpl = expl && expl.indexOf('暫未提供') === -1 && expl.indexOf('暫只提供') === -1;
  if (hasRealExpl) {
    card.appendChild(el('div', { class: 'explanation' },
      el('span', { class: 'label' }, '解析'),
      el('div', { class: 'text' }, expl),
    ));
  }
}

// ----- 进度条 -----
function updateProgress() {
  const total = State.queue.length;
  const cur = State.cursor + (State.answered ? 1 : 0);
  const pct = total > 0 ? Math.round(cur * 100 / total) : 0;
  $('#progress-fill').style.width = pct + '%';
  const btnPrev = $('#btn-prev');
  const btnNext = $('#btn-next');
  btnPrev.disabled = State.cursor === 0;
  btnNext.textContent = (State.cursor >= total - 1 && State.answered) ? '完成 ✓' : '下一題 ›';
  if (!State.answered) {
    btnNext.disabled = true;
  } else {
    btnNext.disabled = false;
  }
}

function nextQuestion() {
  if (!State.answered) return;
  if (State.cursor >= State.queue.length - 1) {
    showResult();
    return;
  }
  State.cursor++;
  State.selectedAnswer = null;
  State.answered = false;
  // 顺序模式：记录 cursor
  if (State.currentMode === 'sequential') {
    const bank = getBank(State.currentPaper);
    const p = getPaperProgress(State.currentPaper);
    // 用全局 question id 找进度
    const curGlobalIdx = bank.questions.findIndex(q => q.id === State.queue[State.cursor].id);
    if (curGlobalIdx >= 0) p.sequentialCursor = curGlobalIdx;
    p._updatedAt = Date.now();
    saveState();
  }
  renderQuestion();
  updateProgress();
}

function prevQuestion() {
  if (State.cursor === 0) return;
  State.cursor--;
  State.selectedAnswer = null;
  State.answered = false;
  renderQuestion();
  updateProgress();
}

// ----- 结果页 -----
function showResult() {
  showBottombar(false);
  const bank = getBank(State.currentPaper);
  setTopbar(bank.label, '完成', '');
  const p = getPaperProgress(State.currentPaper);
  // 统计本次测验的正确率（用 randomHistory 或重新统计）
  // 简单：本次 queue 中已答的题数 = queue.length，但 "正确数" 需要重新追踪
  // 我们在 selectAnswer 时已存了历史（仅 random 模式）；其它模式没有，那就用 stats 增量
  // 为简化，展示全局 stats
  const total = p.stats.answered;
  const correct = p.stats.correct;
  const acc = total > 0 ? Math.round(correct * 100 / total) : 0;

  const view = $('#view');
  view.innerHTML = '';
  view.appendChild(el('div', { class: 'score-card ' + (acc >= 60 ? 'success' : 'fail') },
    el('div', { class: 'lbl' }, '本題庫歷史正確率'),
    el('div', { class: 'big-num' }, acc + '%'),
    el('div', { class: 'lbl' }, `${correct} / ${total} 題正確 · 錯題本 ${p.wrongBook.length} 道`),
  ));
  view.appendChild(el('div', { style: 'display: flex; gap: 8px;' },
    el('button', { class: 'primary block', onclick: () => { State.currentMode = null; renderHome(); } }, '返回首頁'),
    el('button', {
      class: 'ghost block',
      onclick: () => {
        if (State.currentMode === 'random') {
          showRandomSetup(bank);
        } else if (State.currentMode === 'sequential') {
          State.cursor = 0;
          startQuiz();
        } else if (State.currentMode === 'errors') {
          enterMode('errors');
        } else {
          renderHome();
        }
      },
    }, '再練一次'),
  ));
}

function exitQuiz() {
  State.currentMode = null;
  State.queue = [];
  State.cursor = 0;
  State.selectedAnswer = null;
  State.answered = false;
  renderHome();
}

// ============ 云同步 UI ============
// Re-rendered on every renderHome(); also self-refreshes via 'syncstatus' event.
function renderSyncBadge() {
  const badge = el('div', { class: 'sync-badge', id: 'sync-badge' });
  applySyncBadgeState(badge, window.Sync ? Sync.getStatus() : { status: 'disabled' });
  return badge;
}
function applySyncBadgeState(badge, s) {
  if (!badge) return;
  const map = {
    disabled: { cls: 'disabled', text: '☁ 雲同步未啟用', title: '在 js/config.js 填入 Supabase 憑證即可啟用' },
    idle:     { cls: 'ok',       text: '✓ 已同步',       title: s.lastSync ? '上次同步：' + new Date(s.lastSync).toLocaleTimeString() : '' },
    syncing:  { cls: 'busy',     text: '⟳ 同步中…',     title: '' },
    error:    { cls: 'err',      text: '⚠ 同步失敗',    title: s.error || '' },
  };
  const m = map[s.status] || map.disabled;
  badge.className = 'sync-badge ' + m.cls;
  badge.textContent = m.text;
  badge.title = m.title;
}
window.addEventListener('syncstatus', (e) => {
  applySyncBadgeState(document.getElementById('sync-badge'), e.detail);
});

// ============ 启动同步：拉云端、按 last-write-wins 合并 ============
async function syncOnLoad() {
  if (!window.Sync || !Sync.isEnabled()) return;
  const cloudMap = await Sync.pull();
  if (!cloudMap) return;
  let changed = false;
  for (const [paperKey, row] of Object.entries(cloudMap)) {
    const cloudMs = row.updated_at ? new Date(row.updated_at).getTime() : 0;
    const localProg = State.progress[paperKey];
    const localMs = (localProg && localProg._updatedAt) || 0;
    if (!localProg || cloudMs > localMs) {
      // Cloud is newer or local missing → take cloud
      State.progress[paperKey] = row.progress;
      // Preserve a local _updatedAt mirror so future comparisons work
      State.progress[paperKey]._updatedAt = cloudMs;
      changed = true;
    }
  }
  if (changed) {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(State.progress)); } catch {}
    // Re-render home so stats reflect merged data
    if (!State.currentMode) renderHome();
  }
  // If local had unsynced changes (no cloud row or local newer), push now
  if (window.Sync) Sync.push(State.progress);
}

// ============ 初始化 ============
function init() {
  loadState();
  $('#btn-exit').addEventListener('click', exitQuiz);
  $('#btn-next').addEventListener('click', nextQuestion);
  $('#btn-prev').addEventListener('click', prevQuestion);
  // Initialize cloud sync (no-op if config missing).
  // CONFIG comes from js/config.js (separate file so credentials live outside this code).
  if (window.Sync && window.CONFIG) {
    Sync.init(CONFIG.SUPABASE_URL, CONFIG.SUPABASE_ANON_KEY);
  }
  renderHome();
  // Pull cloud state in the background; updates UI when done.
  syncOnLoad();
}

// ============ 题目举报 ============
const REPORT_REASONS = [
  { key: 'wrong_answer',      label: '答案疑似錯誤',  needSuggested: true },
  { key: 'duplicate_options', label: '選項有重複',    needSuggested: false },
  { key: 'ocr_garbage',       label: '題目/選項亂碼', needSuggested: false },
  { key: 'missing_options',   label: '選項不足 4 個', needSuggested: false },
  { key: 'other',             label: '其他問題',      needSuggested: false },
];

function openReportModal(q) {
  // Build modal
  const modal = el('div', { class: 'modal-overlay', id: 'report-modal' },
    el('div', { class: 'modal-card' },
      el('div', { class: 'modal-title' },
        '⚠ 舉報題目問題',
        el('button', { class: 'modal-close', onclick: closeReportModal }, '×'),
      ),
      el('div', { class: 'modal-qno' }, `${State.currentPaper || ''} ${q.no || ''}`),
      // Reason radio chips
      el('div', { class: 'field-label' }, '問題類型'),
      el('div', { class: 'chip-group', id: 'report-reason-group' },
        ...REPORT_REASONS.map((r, i) => el('button', {
          class: 'chip' + (i === 0 ? ' selected' : ''),
          dataset: { reason: r.key },
          onclick: () => {
            modal.querySelectorAll('#report-reason-group .chip').forEach(c => c.classList.remove('selected'));
            modal.querySelector(`#report-reason-group .chip[data-reason="${r.key}"]`).classList.add('selected');
            // Show/hide suggested-answer row
            const sg = modal.querySelector('#suggested-row');
            sg.style.display = r.needSuggested ? '' : 'none';
          },
        }, r.label)),
      ),
      // Suggested answer
      el('div', { id: 'suggested-row', class: 'field-row', style: 'display: none; margin-top: 12px;' },
        el('div', { class: 'field-label' }, '你認為正確答案是'),
        el('div', { class: 'chip-group', id: 'suggested-answer-group' },
          ...['A', 'B', 'C', 'D'].map(l => el('button', {
            class: 'chip small',
            dataset: { letter: l },
            onclick: () => {
              modal.querySelectorAll('#suggested-answer-group .chip').forEach(c => c.classList.remove('selected'));
              modal.querySelector(`#suggested-answer-group .chip[data-letter="${l}"]`).classList.add('selected');
            },
          }, l)),
        ),
      ),
      // Note
      el('div', { class: 'field-row', style: 'margin-top: 12px;' },
        el('div', { class: 'field-label' }, '補充說明（可選）'),
        el('textarea', {
          id: 'report-note',
          class: 'text-area',
          rows: 3,
          placeholder: '例如：PDF 第 39 頁上 Q166 的選項是...',
        }),
      ),
      // Submit
      el('div', { class: 'modal-actions' },
        el('button', { class: 'ghost', onclick: closeReportModal }, '取消'),
        el('button', {
          class: 'primary',
          id: 'report-submit-btn',
          onclick: () => submitReportFromModal(q),
        }, '送出'),
      ),
      el('div', { class: 'modal-sync-hint', id: 'report-status' }, ''),
    ),
  );
  document.body.appendChild(modal);
}

function closeReportModal() {
  const m = document.getElementById('report-modal');
  if (m) m.remove();
}

async function submitReportFromModal(q) {
  const modal = document.getElementById('report-modal');
  if (!modal) return;
  const reasonChip = modal.querySelector('#report-reason-group .chip.selected');
  const reason = reasonChip ? reasonChip.dataset.reason : null;
  if (!reason) {
    alert('請選擇問題類型');
    return;
  }
  const sgChip = modal.querySelector('#suggested-answer-group .chip.selected');
  const suggested = sgChip ? sgChip.dataset.letter : null;
  const note = (modal.querySelector('#report-note').value || '').trim();
  const statusEl = modal.querySelector('#report-status');
  const submitBtn = modal.querySelector('#report-submit-btn');

  submitBtn.disabled = true;
  submitBtn.textContent = '送出中…';

  const report = {
    paperKey: State.currentPaper,
    questionId: q.id,
    questionNo: q.no,
    reason,
    note,
    suggestedAnswer: suggested,
  };

  // Always keep a local copy (works even without cloud)
  const LOCAL_KEY = 'iiqe-local-reports';
  let localReports = [];
  try { localReports = JSON.parse(localStorage.getItem(LOCAL_KEY) || '[]'); } catch {}
  localReports.push({ ...report, ts: Date.now() });
  localStorage.setItem(LOCAL_KEY, JSON.stringify(localReports));

  // Try cloud submission
  if (window.Sync && Sync.isEnabled()) {
    const res = await Sync.submitReport(report);
    if (res.ok) {
      statusEl.textContent = '✓ 已送出，感謝你的回報！';
      setTimeout(closeReportModal, 900);
    } else {
      statusEl.textContent = '⚠ 雲端送出失敗（已存本地，下次同步會重試）：' + (res.error || '');
      submitBtn.disabled = false;
      submitBtn.textContent = '重試';
    }
  } else {
    statusEl.textContent = '✓ 已記錄到本地（雲同步未啟用）';
    setTimeout(closeReportModal, 900);
  }
}

document.addEventListener('DOMContentLoaded', init);
