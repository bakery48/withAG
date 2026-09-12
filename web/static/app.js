// withAG - スマホ側クライアント
(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const log = $('log'), input = $('input'), composer = $('composer');
  const dot = $('dot'), statusText = $('statusText');
  const gate = $('gate'), gateErr = $('gateErr');
  const jump = $('jump'), panel = $('panel'), panelBody = $('panelBody');

  const KEY = 'withag_token';
  let token = new URL(location.href).searchParams.get('token') || localStorage.getItem(KEY) || '';
  if (new URL(location.href).searchParams.get('token')) {
    localStorage.setItem(KEY, token);
    history.replaceState(null, '', location.pathname); // URL から token を消す
  }

  let ws = null, retry = 0, lastSeq = 0, stream = null, unread = 0;
  const seen = new Set();
  const baseTitle = 'withAG';

  // ---------- 表示ユーティリティ ----------
  const escapeHtml = (s) => s.replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));

  // 最低限の Markdown（コードブロックとインラインコードだけ）
  function render(text) {
    const parts = String(text).split(/```/);
    return parts.map((part, i) => {
      if (i % 2 === 1) {
        const body = part.replace(/^[\w+-]*\n?/, '');
        return `<pre><code>${escapeHtml(body)}</code></pre>`;
      }
      return escapeHtml(part).replace(/`([^`\n]+)`/g, '<code>$1</code>');
    }).join('');
  }

  const atBottom = () => log.scrollHeight - log.scrollTop - log.clientHeight < 120;

  function scrollToBottom(force) {
    if (force || atBottom()) {
      requestAnimationFrame(() => { log.scrollTop = log.scrollHeight; });
      clearUnread();
    } else {
      jump.classList.remove('hidden');
    }
  }

  function timeLabel(ts) {
    const d = new Date((ts || Date.now() / 1000) * 1000);
    return d.toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' });
  }

  function addMessage(item) {
    if (item.seq) {
      if (seen.has(item.seq)) return document.querySelector(`[data-seq="${item.seq}"]`);
      seen.add(item.seq);
      lastSeq = Math.max(lastSeq, item.seq);
    }
    const wrap = document.createElement('div');
    wrap.className = `msg ${item.role}${item.pending ? ' pending' : ''}`;
    if (item.seq) wrap.dataset.seq = item.seq;
    wrap.innerHTML = `<div class="bubble">${render(item.text)}</div>` +
      `<div class="meta">${item.role === 'user' ? 'あなた' : item.role === 'system' ? '' : 'Antigravity'} ${timeLabel(item.ts)}</div>`;
    log.appendChild(wrap);
    return wrap;
  }

  function addSystem(text) {
    addMessage({ role: 'system', text, ts: Date.now() / 1000 });
    scrollToBottom();
  }

  // ---------- ストリーミング表示 ----------
  function pushDelta(text) {
    if (!stream) {
      const wrap = document.createElement('div');
      wrap.className = 'msg assistant streaming';
      wrap.innerHTML = '<div class="bubble typing"></div><div class="meta">Antigravity 応答中…</div>';
      log.appendChild(wrap);
      stream = { wrap, buf: '' };
    }
    stream.buf += text;
    stream.wrap.querySelector('.bubble').innerHTML = render(stream.buf.trim());
    scrollToBottom();
  }

  function clearStream() {
    if (stream) { stream.wrap.remove(); stream = null; }
  }

  // ---------- 通知 ----------
  let audioCtx = null;
  function beep() {
    try {
      audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
      if (audioCtx.state === 'suspended') audioCtx.resume();
      const osc = audioCtx.createOscillator(), gain = audioCtx.createGain();
      osc.connect(gain); gain.connect(audioCtx.destination);
      osc.frequency.value = 880;
      gain.gain.setValueAtTime(0.001, audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.15, audioCtx.currentTime + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.25);
      osc.start(); osc.stop(audioCtx.currentTime + 0.26);
    } catch (_) { /* 音が鳴らなくても動作に支障はない */ }
  }

  function notify(text) {
    beep();
    if (navigator.vibrate) { try { navigator.vibrate(60); } catch (_) {} }
    if (document.hidden) {
      unread += 1;
      document.title = `(${unread}) ${baseTitle}`;
      if (window.Notification && Notification.permission === 'granted') {
        try { new Notification('Antigravity', { body: text.slice(0, 120), tag: 'withag' }); } catch (_) {}
      }
    }
  }

  function clearUnread() {
    unread = 0;
    document.title = baseTitle;
  }

  // ---------- WebSocket ----------
  function setStatus(state, text) {
    dot.className = `dot ${state}`;
    statusText.textContent = text;
  }

  function connect() {
    if (!token) { gate.classList.remove('hidden'); return; }
    gate.classList.add('hidden');
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${location.host}/ws?token=${encodeURIComponent(token)}&since=${lastSeq}`);

    ws.onopen = () => { retry = 0; setStatus('ok', '接続済み'); refreshStatus(); };

    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === 'hello') {
        (msg.items || []).forEach(addMessage);
        lastSeq = Math.max(lastSeq, msg.last_seq || 0);
        applyStatus({ antigravity: msg.antigravity, watcher: msg.watcher });
        scrollToBottom(true);
      } else if (msg.type === 'message') {
        clearStream();
        addMessage(msg.item);
        scrollToBottom();
        if (msg.item.role === 'assistant') notify(msg.item.text);
      } else if (msg.type === 'delta') {
        pushDelta(msg.text);
      } else if (msg.type === 'settled') {
        clearStream();
      } else if (msg.type === 'send_result') {
        const el = document.querySelector(`[data-seq="${msg.seq}"]`);
        if (el) {
          el.classList.remove('pending');
          if (!msg.ok) {
            el.classList.add('failed');
            el.querySelector('.meta').textContent = `送信失敗: ${msg.message}`;
          }
        }
      } else if (msg.type === 'status') {
        applyStatus(msg);
      }
    };

    ws.onclose = (ev) => {
      ws = null;
      if (ev.code === 4401) {
        localStorage.removeItem(KEY);
        token = '';
        gateErr.textContent = 'token が違います。';
        gate.classList.remove('hidden');
        setStatus('ng', '認証エラー');
        return;
      }
      retry += 1;
      const wait = Math.min(1000 * 2 ** Math.min(retry, 5), 15000);
      setStatus('ng', `切断 - ${Math.round(wait / 1000)}秒後に再接続`);
      setTimeout(connect, wait);
    };

    ws.onerror = () => { try { ws.close(); } catch (_) {} };
  }

  // 画面復帰時はすぐ繋ぎ直す
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
      clearUnread();
      if (!ws || ws.readyState > 1) { retry = 0; connect(); }
    }
  });
  setInterval(() => { if (ws && ws.readyState === 1) ws.send('ping'); }, 25000);

  // ---------- 状態表示 ----------
  let lastStatus = {};
  function applyStatus(data) {
    lastStatus = { ...lastStatus, ...data };
    const ag = lastStatus.antigravity || {};
    const wt = lastStatus.watcher || {};
    if (!ag.window_found) setStatus('warn', 'Antigravity 未検出');
    else if (!wt.exists) setStatus('warn', 'Conversation.md 未検出');
    else if (ws && ws.readyState === 1) setStatus('ok', ag.window_title || '接続済み');
    renderPanel();
  }

  function renderPanel() {
    const ag = lastStatus.antigravity || {};
    const wt = lastStatus.watcher || {};
    const rows = [
      ['Antigravity', ag.window_found ? `検出: ${ag.window_title}` : (ag.detail || '未検出')],
      ['監視ファイル', wt.path || '-'],
      ['ファイル', wt.exists ? `あり (${wt.size} bytes)` : 'なし'],
      ['接続端末', lastStatus.clients ?? '-'],
      ['プッシュ通知', lastStatus.notify ? (lastStatus.notify.enabled ? '有効 (ntfy)' : '無効') : '-'],
    ];
    panelBody.innerHTML = rows.map(([k, v]) => `<dt>${escapeHtml(k)}</dt><dd>${escapeHtml(String(v))}</dd>`).join('');
  }

  async function refreshStatus() {
    try {
      const res = await fetch(`/api/status?token=${encodeURIComponent(token)}`);
      if (res.ok) applyStatus(await res.json());
    } catch (_) {}
  }

  // ---------- 送信 ----------
  async function send() {
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    autoGrow();
    try {
      const res = await fetch('/api/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Token': token },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        addSystem(`送信できませんでした: ${data.detail || res.status}`);
      }
    } catch (err) {
      addSystem(`送信できませんでした: ${err}`);
      input.value = text; // 消えると困るので戻す
      autoGrow();
    }
  }

  function autoGrow() {
    input.style.height = 'auto';
    input.style.height = `${Math.min(input.scrollHeight, window.innerHeight * 0.4)}px`;
  }

  composer.addEventListener('submit', (e) => { e.preventDefault(); send(); });
  input.addEventListener('input', autoGrow);
  input.addEventListener('keydown', (e) => {
    // PC ブラウザからも使えるように: Ctrl/Cmd+Enter で送信
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); send(); }
  });

  log.addEventListener('scroll', () => {
    if (atBottom()) { jump.classList.add('hidden'); clearUnread(); }
  });
  jump.addEventListener('click', () => { jump.classList.add('hidden'); scrollToBottom(true); });

  $('infoBtn').addEventListener('click', () => {
    panel.classList.toggle('hidden');
    if (!panel.classList.contains('hidden')) refreshStatus();
    if (window.Notification && Notification.permission === 'default') {
      try { Notification.requestPermission(); } catch (_) {}
    }
  });
  $('reloadBtn').addEventListener('click', () => location.reload());
  $('logoutBtn').addEventListener('click', () => {
    localStorage.removeItem(KEY);
    location.href = '/';
  });

  $('tokenBtn').addEventListener('click', () => {
    const value = $('tokenInput').value.trim();
    if (!value) return;
    token = value;
    localStorage.setItem(KEY, token);
    gateErr.textContent = '';
    connect();
  });
  $('tokenInput').addEventListener('keydown', (e) => { if (e.key === 'Enter') $('tokenBtn').click(); });

  connect();
})();
