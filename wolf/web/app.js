"use strict";

/* ---------- small helpers ---------- */
const $ = (sel) => document.querySelector(sel);
const store = {
  get(k, d = null) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode */ } },
  del(k) { try { localStorage.removeItem(k); } catch { /* ignore */ } },
};
const esc = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function toast(msg, ms = 3500) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { t.hidden = true; }, ms);
}

/* Minimal, safe markdown: escape first, then add a few formats. */
function md(src) {
  const blocks = [];
  let text = esc(src).replace(/```[^\n]*\n([\s\S]*?)```/g, (_, code) => {
    blocks.push(`<pre><code>${code.replace(/\n$/, "")}</code></pre>`);
    return `\u0000${blocks.length - 1}\u0000`;
  });
  const inline = (s) => s
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  const out = [];
  let list = null;
  const closeList = () => { if (list) { out.push(`</${list}>`); list = null; } };
  for (const line of text.split("\n")) {
    let m;
    if ((m = line.match(/^\u0000(\d+)\u0000$/))) { closeList(); out.push(blocks[+m[1]]); }
    else if ((m = line.match(/^\s*[-*•]\s+(.*)/))) { if (list !== "ul") { closeList(); out.push("<ul>"); list = "ul"; } out.push(`<li>${inline(m[1])}</li>`); }
    else if ((m = line.match(/^\s*\d+[.)]\s+(.*)/))) { if (list !== "ol") { closeList(); out.push("<ol>"); list = "ol"; } out.push(`<li>${inline(m[1])}</li>`); }
    else if ((m = line.match(/^(#{1,3})\s+(.*)/))) { closeList(); out.push(`<h3>${inline(m[2])}</h3>`); }
    else if (!line.trim()) { closeList(); }
    else { closeList(); out.push(`<p>${inline(line)}</p>`); }
  }
  closeList();
  return out.join("").replace(/\u0000(\d+)\u0000/g, (_, i) => blocks[+i]);
}
const plain = (s) => s.replace(/```[\s\S]*?```/g, " ").replace(/[*_`#>]/g, "").replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");

/* ---------- access token ---------- */
(function captureToken() {
  const url = new URL(location.href);
  const t = url.searchParams.get("token");
  if (t) {
    store.set("wolf.token", t);
    url.searchParams.delete("token");
    history.replaceState(null, "", url.pathname + url.search + url.hash);
  }
})();
const token = () => store.get("wolf.token");

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token()}`, ...(opts.headers || {}) },
  });
  if (res.status === 401) { lock(); throw new Error("locked"); }
  return res;
}
function lock() { $("#locked").hidden = false; }
if (!token()) lock();

/* ---------- tabs ---------- */
document.querySelectorAll(".tabs button").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tabs button").forEach((b) => b.setAttribute("aria-selected", String(b === btn)));
    document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${btn.dataset.view}`));
    if (btn.dataset.view === "memory") loadMemory();
    if (btn.dataset.view === "you") loadYou();
  });
});

/* ---------- chat ---------- */
const messagesEl = $("#messages");
const input = $("#input");
const sendBtn = $("#send");
let conversationId = store.get("wolf.conversation");
let transcript = store.get("wolf.transcript", []); // [{role, text, chips?}] for display after reload
let busy = false;

const TOOL_LABELS = {
  remember: "Saved to memory", recall: "Checked memory", update_memory: "Updated a memory",
  forget: "Forgot something", update_profile: "Updated your profile",
};

function scrollDown() { messagesEl.scrollTop = messagesEl.scrollHeight; }

function addMessage(role, text, chips = []) {
  $("#chat-empty")?.remove();
  const row = document.createElement("div");
  row.className = `msg ${role}`;
  const bubble = document.createElement("div");
  bubble.className = "bubble" + (role === "wolf" ? " md" : "");
  if (role === "wolf") bubble.innerHTML = md(text); else bubble.textContent = text;
  row.appendChild(bubble);
  const chipBox = document.createElement("div");
  chipBox.className = "chips";
  chips.forEach((c) => chipBox.append(Object.assign(document.createElement("span"), { className: "chip", textContent: c })));
  if (role === "wolf") bubble.appendChild(chipBox);
  messagesEl.appendChild(row);
  scrollDown();
  return { bubble, chipBox };
}
function addDivider(text) {
  messagesEl.appendChild(Object.assign(document.createElement("div"), { className: "divider", textContent: text }));
}
function saveTranscript() { store.set("wolf.transcript", transcript.slice(-200)); }

for (const m of transcript) m.role === "divider" ? addDivider(m.text) : addMessage(m.role, m.text, m.chips || []);

function autosize() { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 160) + "px"; }
input.addEventListener("input", autosize);
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing && matchMedia("(hover: hover)").matches) {
    e.preventDefault();
    $("#composer").requestSubmit();
  }
});
$("#composer").addEventListener("submit", (e) => { e.preventDefault(); send(input.value, false); });

async function send(text, viaVoice) {
  text = text.trim();
  if (!text || busy) return;
  busy = true;
  sendBtn.disabled = true;
  input.value = "";
  autosize();
  stopSpeaking();
  addMessage("user", text);
  transcript.push({ role: "user", text });
  saveTranscript();

  const { bubble, chipBox } = addMessage("wolf", "");
  bubble.insertAdjacentHTML("afterbegin", '<div class="typing"><span></span><span></span><span></span></div>');
  let reply = "";
  const chips = [];
  let failed = null;

  try {
    const res = await api("/api/chat", { method: "POST", body: JSON.stringify({ conversation_id: conversationId, message: text }) });
    if (!res.ok || !res.body) throw new Error((await res.json().catch(() => ({}))).error || `HTTP ${res.status}`);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    const render = () => {
      bubble.innerHTML = md(reply) || '<div class="typing"><span></span><span></span><span></span></div>';
      bubble.appendChild(chipBox);
      scrollDown();
    };
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const raw = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        const ev = /^event: (.*)$/m.exec(raw)?.[1];
        const data = JSON.parse(/^data: (.*)$/m.exec(raw)?.[1] || "{}");
        if (ev === "start") {
          if (conversationId && data.conversation_id !== conversationId && transcript.length > 1) {
            // The server closed the old conversation (idle or restarted) and started a new one.
            transcript.splice(transcript.length - 1, 0, { role: "divider", text: "New conversation" });
          }
          conversationId = data.conversation_id;
          store.set("wolf.conversation", conversationId);
        } else if (ev === "text") { reply += data.text; render(); }
        else if (ev === "tool") {
          const label = TOOL_LABELS[data.name] || data.name;
          if (!chips.includes(label)) { chips.push(label); chipBox.append(Object.assign(document.createElement("span"), { className: "chip", textContent: label })); }
        } else if (ev === "error") { failed = data.message; }
      }
    }
  } catch (err) {
    if (err.message !== "locked") failed = navigator.onLine ? `Couldn't reach WOLF (${err.message}). Is \`wolf serve\` still running?` : "You're offline.";
  }

  if (failed) {
    bubble.classList.add("error");
    bubble.textContent = failed;
  } else {
    bubble.innerHTML = md(reply.trim() || "…");
    bubble.appendChild(chipBox);
    transcript.push({ role: "wolf", text: reply.trim(), chips });
    saveTranscript();
    speak(reply, viaVoice);
  }
  busy = false;
  sendBtn.disabled = false;
  if (!viaVoice) input.focus({ preventScroll: true });
}

$("#new-chat").addEventListener("click", async () => {
  if (busy) return;
  const id = conversationId;
  conversationId = null;
  transcript = [];
  store.del("wolf.conversation");
  saveTranscript();
  messagesEl.innerHTML = "";
  addDivider("New conversation");
  if (!id) return;
  $("#status").textContent = "Saving what I learned…";
  try {
    const res = await api("/api/end", { method: "POST", body: JSON.stringify({ conversation_id: id }) });
    const data = await res.json();
    if (data.summary) toast(`Saved to journal: ${data.summary}`);
  } catch { /* the server also saves idle conversations on its own */ }
  $("#status").textContent = "";
});

/* ---------- voice ---------- */
const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const micBtn = $("#mic");
const speakBtn = $("#speak-toggle");
let speakOn = store.get("wolf.speak", false);
let recognizer = null;
let handsFree = false; // conversation started by voice: keep listening after WOLF answers

speakBtn.setAttribute("aria-pressed", String(speakOn));
if (!("speechSynthesis" in window)) speakBtn.hidden = true;
speakBtn.addEventListener("click", () => {
  speakOn = !speakOn;
  store.set("wolf.speak", speakOn);
  speakBtn.setAttribute("aria-pressed", String(speakOn));
  if (!speakOn) stopSpeaking();
  toast(speakOn ? "WOLF will read replies aloud" : "Voice replies off", 1800);
});

function stopSpeaking() { if ("speechSynthesis" in window) speechSynthesis.cancel(); }
function speak(text, viaVoice) {
  if (!speakOn || !("speechSynthesis" in window) || !text.trim()) { handsFree = false; return; }
  const u = new SpeechSynthesisUtterance(plain(text));
  u.rate = 1.03;
  u.onend = () => { if (viaVoice && handsFree) listen(); };
  speechSynthesis.speak(u);
}

if (Recognition) {
  micBtn.hidden = false;
  micBtn.addEventListener("click", () => {
    if (recognizer) { handsFree = false; recognizer.stop(); return; }
    handsFree = true;
    listen();
  });
}

function listen() {
  if (!Recognition || recognizer || busy) return;
  stopSpeaking();
  recognizer = new Recognition();
  recognizer.lang = navigator.language || "en-US";
  recognizer.interimResults = true;
  recognizer.continuous = false;
  let finalText = "";
  micBtn.classList.add("listening");
  $("#status").textContent = "Listening…";
  recognizer.onresult = (e) => {
    let interim = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const r = e.results[i];
      if (r.isFinal) finalText += r[0].transcript; else interim += r[0].transcript;
    }
    input.value = (finalText + interim).trim();
    autosize();
  };
  recognizer.onerror = (e) => {
    handsFree = false;
    if (e.error === "not-allowed" || e.error === "service-not-allowed") {
      toast(location.protocol === "https:" || location.hostname === "localhost"
        ? "Microphone access was blocked. Allow it in your browser settings."
        : "Voice input needs a secure (https) connection on this device. See the README.");
    }
  };
  recognizer.onend = () => {
    recognizer = null;
    micBtn.classList.remove("listening");
    $("#status").textContent = "";
    const text = input.value.trim();
    if (text) send(text, true); else handsFree = false;
  };
  try { recognizer.start(); } catch { recognizer = null; micBtn.classList.remove("listening"); }
}

/* ---------- memory ---------- */
let memTimer;
$("#mem-search").addEventListener("input", () => { clearTimeout(memTimer); memTimer = setTimeout(loadMemory, 250); });

async function loadMemory() {
  const q = $("#mem-search").value.trim();
  const list = $("#mem-list");
  try {
    const data = await (await api(`/api/memory${q ? `?q=${encodeURIComponent(q)}` : ""}`)).json();
    $("#mem-count").textContent = q ? `${data.memories.length} found` : `${data.memories.length} memories`;
    list.innerHTML = "";
    if (!data.memories.length) {
      list.innerHTML = `<li class="muted">${q ? "Nothing matches." : "Nothing yet. Chat with WOLF and it will start remembering what matters to you."}</li>`;
      return;
    }
    for (const m of data.memories) {
      const li = document.createElement("li");
      const tags = m.tags.length ? ` · ${m.tags.join(", ")}` : "";
      li.innerHTML = `<div class="text">${esc(m.text)}<div class="meta">${esc(new Date(m.updated).toLocaleDateString())}${esc(tags)}</div></div>
        <button class="icon-btn forget" title="Forget" aria-label="Forget this memory">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/></svg></button>`;
      li.querySelector(".forget").addEventListener("click", async () => {
        if (!confirm(`Forget this?\n\n“${m.text}”`)) return;
        await api(`/api/memory/${encodeURIComponent(m.id)}`, { method: "DELETE" });
        li.remove();
        toast("Forgotten", 1500);
      });
      list.appendChild(li);
    }
  } catch (e) { if (e.message !== "locked") list.innerHTML = '<li class="muted">Couldn\'t load memories.</li>'; }
}

/* ---------- you ---------- */
async function loadYou() {
  try {
    const [p, j] = await Promise.all([api("/api/profile").then((r) => r.json()), api("/api/journal").then((r) => r.json())]);
    $("#profile").innerHTML = p.profile.trim()
      ? md(p.profile.replace(/^# About me\s*/, ""))
      : '<p class="muted">Empty for now. As you talk, WOLF builds a short profile of you here.</p>';
    const jl = $("#journal");
    jl.innerHTML = "";
    if (!j.journal.length) jl.innerHTML = '<li class="muted">No conversations yet.</li>';
    for (const line of j.journal.slice().reverse()) {
      jl.appendChild(Object.assign(document.createElement("li"), { textContent: line.replace(/^- /, "") }));
    }
  } catch (e) { if (e.message !== "locked") toast("Couldn't load your profile."); }
}

/* ---------- install / offline shell ---------- */
if ("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
