/*
 * Floating AI assistant - University Medical Center
 * - sends questions to POST /chatbot/message (JSON, CSRF header)
 * - renders replies safely (never uses innerHTML for model text)
 * - keeps the conversation in sessionStorage so it survives page changes in the same tab
 */
(function () {
    'use strict';

    // ------------------------------------------------------------------
    // Pure helpers (no DOM) - tested separately with Node
    // ------------------------------------------------------------------
    function parseInline(text) {
        var out = [], re = /\*\*([^*\n]+)\*\*/g, last = 0, m;
        while ((m = re.exec(text)) !== null) {
            if (m.index > last) out.push({ t: text.slice(last, m.index), b: false });
            out.push({ t: m[1], b: true });
            last = m.index + m[0].length;
        }
        if (last < text.length) out.push({ t: text.slice(last), b: false });
        return out;
    }

    /** Turns "- item" lines into lists and **x** into bold; everything else is plain paragraphs. */
    function parseRich(text) {
        var blocks = [], list = null;
        String(text).replace(/\r/g, '').split('\n').forEach(function (line) {
            var bullet = /^\s*[-*\u2022]\s+(.*)$/.exec(line);
            if (bullet) {
                if (!list) { list = { type: 'ul', items: [] }; blocks.push(list); }
                list.items.push(parseInline(bullet[1]));
            } else if (line.trim() === '') {
                list = null;
            } else {
                list = null;
                blocks.push({ type: 'p', inline: parseInline(line) });
            }
        });
        return blocks;
    }

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { parseInline: parseInline, parseRich: parseRich };
    }
    if (typeof document === 'undefined') return;

    // ------------------------------------------------------------------
    // Widget
    // ------------------------------------------------------------------
    var root = document.getElementById('umcChat');
    if (!root) return;

    var endpoint = root.dataset.endpoint;
    var maxLength = parseInt(root.dataset.maxLength, 10) || 500;
    var historyTurns = parseInt(root.dataset.historyTurns, 10) || 6;
    var STORAGE_KEY = 'umc_chat_v1';
    var REQUEST_TIMEOUT_MS = 45000;

    var toggleBtn = document.getElementById('umcChatToggle');
    var panel = document.getElementById('umcChatPanel');
    var closeBtn = document.getElementById('umcChatClose');
    var clearBtn = document.getElementById('umcChatClear');
    var list = document.getElementById('umcChatMessages');
    var chips = document.getElementById('umcChatChips');
    var form = document.getElementById('umcChatForm');
    var input = document.getElementById('umcChatInput');
    var sendBtn = document.getElementById('umcChatSend');
    var counter = document.getElementById('umcChatCounter');

    var messages = [];   // [{role: 'user'|'assistant', text}] - only successful turns
    var busy = false;

    var WELCOME = 'Hello! I\'m the University Medical Center assistant. I can help with opening hours, ' +
        'tokens, registration, the pharmacy, and general first-aid or health questions.\n\n' +
        '**I can\'t diagnose or prescribe** - for that, please see a doctor at the Medical Center.';

    // ---- storage (may be unavailable, e.g. private mode) ----------------
    function loadState() {
        try {
            var raw = window.sessionStorage.getItem(STORAGE_KEY);
            if (!raw) return { messages: [], open: false };
            var data = JSON.parse(raw);
            return {
                messages: Array.isArray(data.messages) ? data.messages.slice(-60) : [],
                open: !!data.open
            };
        } catch (e) { return { messages: [], open: false }; }
    }
    function saveState() {
        try {
            window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
                messages: messages.slice(-60),
                open: !panel.hidden
            }));
        } catch (e) { /* ignore */ }
    }

    // ---- DOM helpers ------------------------------------------------------
    function appendInline(parent, parts) {
        parts.forEach(function (p) {
            if (p.b) {
                var s = document.createElement('strong');
                s.textContent = p.t;
                parent.appendChild(s);
            } else {
                parent.appendChild(document.createTextNode(p.t));
            }
        });
    }

    function renderInto(el, text) {
        parseRich(text).forEach(function (block) {
            if (block.type === 'ul') {
                var ul = document.createElement('ul');
                block.items.forEach(function (inline) {
                    var li = document.createElement('li');
                    appendInline(li, inline);
                    ul.appendChild(li);
                });
                el.appendChild(ul);
            } else {
                var p = document.createElement('p');
                appendInline(p, block.inline);
                el.appendChild(p);
            }
        });
    }

    function scrollToBottom() { list.scrollTop = list.scrollHeight; }

    function addBubble(role, text, variant) {
        var el = document.createElement('div');
        el.className = 'umc-chat__bubble umc-chat__bubble--' + (variant || role);
        if (role === 'user') { el.textContent = text; } else { renderInto(el, text); }
        list.appendChild(el);
        scrollToBottom();
        return el;
    }

    function showTyping() {
        var el = document.createElement('div');
        el.className = 'umc-chat__bubble umc-chat__bubble--assistant';
        el.setAttribute('aria-label', 'The assistant is typing');
        el.innerHTML = '<span class="umc-chat__typing"><span></span><span></span><span></span></span>';
        list.appendChild(el);
        scrollToBottom();
        return el;
    }

    function setBusy(state) {
        busy = state;
        sendBtn.disabled = state;
        input.disabled = state;
        list.setAttribute('aria-busy', state ? 'true' : 'false');
    }

    function autosize() {
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 110) + 'px';
    }

    function updateCounter() {
        var n = input.value.length;
        if (n > maxLength * 0.8) {
            counter.textContent = n + ' / ' + maxLength;
            counter.classList.toggle('umc-chat__counter--warn', n >= maxLength);
        } else {
            counter.textContent = '';
        }
    }

    function renderAll() {
        list.innerHTML = '';
        addBubble('assistant', WELCOME);
        messages.forEach(function (m) { addBubble(m.role, m.text); });
        chips.hidden = messages.length > 0;
    }

    // ---- open / close -------------------------------------------------------
    function openPanel() {
        panel.hidden = false;
        root.classList.add('umc-chat--open');
        toggleBtn.setAttribute('aria-expanded', 'true');
        toggleBtn.setAttribute('aria-label', 'Close the AI assistant');
        scrollToBottom();
        input.focus();
        saveState();
    }
    function closePanel(returnFocus) {
        panel.hidden = true;
        root.classList.remove('umc-chat--open');
        toggleBtn.setAttribute('aria-expanded', 'false');
        toggleBtn.setAttribute('aria-label', 'Open the AI assistant');
        if (returnFocus) toggleBtn.focus();
        saveState();
    }

    // ---- talking to the server ----------------------------------------------
    function csrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    function send(rawText) {
        var text = (rawText || '').trim();
        if (!text || busy) return;
        if (text.length > maxLength) {
            addBubble('assistant', 'Please keep your message under ' + maxLength + ' characters.', 'error');
            return;
        }

        chips.hidden = true;
        addBubble('user', text);
        input.value = '';
        autosize();
        updateCounter();
        setBusy(true);
        var typing = showTyping();

        var controller = new AbortController();
        var timer = setTimeout(function () { controller.abort(); }, REQUEST_TIMEOUT_MS);
        var history = messages.slice(-historyTurns * 2);

        fetch(endpoint, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-CSRFToken': csrfToken()
            },
            body: JSON.stringify({ message: text, history: history }),
            signal: controller.signal
        })
        .then(function (res) {
            return res.json().then(function (data) { return { status: res.status, data: data }; },
                                   function () { return { status: res.status, data: null }; });
        })
        .then(function (res) {
            typing.remove();
            var data = res.data;
            if (data && typeof data.reply === 'string') {
                var variant = data.ok ? ((data.kind === 'emergency' || data.kind === 'safety') ? 'alert' : 'assistant') : 'error';
                addBubble('assistant', data.reply, variant);
                if (data.ok) {
                    messages.push({ role: 'user', text: text });
                    messages.push({ role: 'assistant', text: data.reply });
                    saveState();
                }
            } else if (res.status === 400) {
                addBubble('assistant', 'Your session has expired. Please refresh the page and try again.', 'error');
            } else {
                addBubble('assistant', 'Something went wrong. Please try again in a moment.', 'error');
            }
        })
        .catch(function (err) {
            typing.remove();
            var timedOut = err && err.name === 'AbortError';
            addBubble('assistant', timedOut
                ? 'The assistant took too long to answer. Please try again.'
                : 'I couldn\'t reach the assistant. Please check your connection and try again.', 'error');
        })
        .then(function () {
            clearTimeout(timer);
            setBusy(false);
            if (!panel.hidden) input.focus();
        });
    }

    // ---- events -----------------------------------------------------------------
    toggleBtn.addEventListener('click', function () {
        if (panel.hidden) { openPanel(); } else { closePanel(false); }
    });
    closeBtn.addEventListener('click', function () { closePanel(true); });
    clearBtn.addEventListener('click', function () {
        if (busy) return;
        messages = [];
        saveState();
        renderAll();
        input.focus();
    });
    form.addEventListener('submit', function (e) {
        e.preventDefault();
        send(input.value);
    });
    input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
            e.preventDefault();
            send(input.value);
        }
    });
    input.addEventListener('input', function () { autosize(); updateCounter(); });
    chips.addEventListener('click', function (e) {
        var chip = e.target.closest('.umc-chat__chip');
        if (chip) send(chip.textContent);
    });
    panel.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') { e.stopPropagation(); closePanel(true); }
    });

    // ---- start -------------------------------------------------------------------
    var state = loadState();
    messages = state.messages.filter(function (m) {
        return m && (m.role === 'user' || m.role === 'assistant') && typeof m.text === 'string';
    });
    renderAll();
    if (state.open) openPanel();
})();
