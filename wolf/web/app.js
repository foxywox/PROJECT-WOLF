"use strict";

/* ---------- small helpers ---------- */
const $ = (sel) => document.querySelector(sel);
const store = {
  get(k, d = null) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode */ } },
  del(k) { try { localStorage.removeItem(k); } catch { /* ignore */ } },
};
const el = (tag, cls, text) => Object.assign(document.createElement(tag), cls ? { className: cls } : {}, text != null ? { textContent: text } : {});
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
const LOADERS = { schedule: () => loadSchedule(), memory: () => loadMemoryTab(), settings: () => loadSettings(), project: () => loadProject() };
function showView(name) {
  // The project page isn't a tab; Settings stays highlighted while it's open.
  const tab = name === "project" ? "settings" : name;
  document.querySelectorAll(".tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.view === tab)));
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${name}`));
  if (name !== "project") stopProjectRefresh();
  LOADERS[name]?.();
}
document.querySelectorAll(".tabs button").forEach((btn) => btn.addEventListener("click", () => showView(btn.dataset.view)));

/* ---------- friendly dates ---------- */
function dayLabel(date) {
  const d = new Date(date), today = new Date();
  const start = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((start(today) - start(d)) / 86400000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  if (diff < 7) return d.toLocaleDateString(undefined, { weekday: "long" });
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: d.getFullYear() === today.getFullYear() ? undefined : "numeric" });
}
function ago(date) {
  const m = Math.round((Date.now() - new Date(date).getTime()) / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m} min ago`;
  if (m < 60 * 24) return `${Math.round(m / 60)} h ago`;
  return dayLabel(date);
}

/* ---------- chat ---------- */
const messagesEl = $("#messages");
const input = $("#input");
const sendBtn = $("#send");
let conversationId = store.get("wolf.conversation");
let transcript = store.get("wolf.transcript", []); // [{role, text, chips?}] for display after reload
let busy = false;

const TOOL_LABELS = {
  remember: "Saved to memory", recall: "Checked memory", update_memory: "Updated a memory",
  forget: "Forgot something", update_profile: "Updated your profile", current_time: "Checked the time",
  read_plan: "Read the project plan", list_forum: "Read the forum", read_thread: "Read a forum thread",
  post_to_forum: "Posted in the forum", add_reminder: "Set a reminder", list_reminders: "Checked reminders",
  complete_reminder: "Ticked off a reminder", calendar_events: "Checked your calendar",
};
const welcome = $("#chat-empty").cloneNode(true);
function wireSuggestions(root) {
  root.querySelectorAll("#suggestions button").forEach((b) => b.addEventListener("click", () => {
    if (b.dataset.send) return send(b.dataset.send, false);
    input.value = b.dataset.fill || "";
    autosize();
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
  }));
}

function scrollDown() { messagesEl.scrollTop = messagesEl.scrollHeight; }
const THINKING = '<div class="thinking"><span class="typing"><span></span><span></span><span></span></span>WOLF is thinking…</div>';

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
wireSuggestions(document);

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
  const userRow = addMessage("user", text).bubble.parentElement;
  transcript.push({ role: "user", text });
  saveTranscript();

  const { bubble, chipBox } = addMessage("wolf", "");
  bubble.insertAdjacentHTML("afterbegin", THINKING);
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
      bubble.innerHTML = md(reply) || THINKING;
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
            const rows = messagesEl.querySelectorAll(".msg.user");
            const lastUser = rows[rows.length - 1];
            lastUser?.before(Object.assign(document.createElement("div"), { className: "divider", textContent: "New conversation" }));
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
    if (err.message !== "locked") failed = navigator.onLine ? "Couldn't reach WOLF. Check that it's still running on your computer, then try again." : "You're offline. Reconnect, then try again.";
  }

  if (failed) {
    bubble.classList.add("error");
    bubble.textContent = failed;
    const retry = Object.assign(document.createElement("button"), { className: "retry", type: "button", textContent: "Try again" });
    retry.addEventListener("click", () => {
      if (busy) return;
      bubble.parentElement.remove();
      userRow.remove();
      transcript.pop();
      saveTranscript();
      send(text, viaVoice);
    });
    bubble.appendChild(retry);
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
  const fresh = welcome.cloneNode(true);
  messagesEl.appendChild(fresh);
  wireSuggestions(fresh);
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
      li.innerHTML = `<div class="text">${esc(m.text)}<div class="meta">${esc(dayLabel(m.updated))}${esc(tags)}</div></div>
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
async function loadSchedule() {
  try {
    const [rem, cal] = await Promise.all([api("/api/reminders").then((r) => r.json()), api("/api/calendar").then((r) => r.json())]);
    renderReminders(rem);
    renderCalendar(cal);
  } catch (e) { if (e.message !== "locked") toast("Couldn't load your schedule."); }
}

async function loadMemoryTab() {
  loadMemory();
  try {
    const [p, j] = await Promise.all([api("/api/profile").then((r) => r.json()), api("/api/journal").then((r) => r.json())]);
    $("#profile").innerHTML = p.profile.trim()
      ? md(p.profile.replace(/^# About me\s*/, ""))
      : '<p class="muted">Empty for now. As you talk, WOLF writes a short summary of what matters to you here.</p>';
    const jl = $("#journal");
    jl.innerHTML = "";
    if (!j.journal.length) jl.innerHTML = '<li class="muted">No conversations yet. Your first one will show up here.</li>';
    for (const line of j.journal.slice().reverse()) {
      const m = /^- (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}): (.*)$/.exec(line);
      const li = document.createElement("li");
      const t = document.createElement("time");
      t.textContent = m ? dayLabel(`${m[1]}T${m[2]}`) : "";
      li.append(t, Object.assign(document.createElement("span"), { textContent: m ? m[3] : line.replace(/^- /, "") }));
      jl.appendChild(li);
    }
  } catch (e) { if (e.message !== "locked") toast("Couldn't load your memory."); }
}

async function loadSettings() {
  try {
    const [c, per, cal] = await Promise.all([
      api("/api/components").then((r) => r.json()),
      api("/api/personality").then((r) => r.json()),
      api("/api/calendar").then((r) => r.json()),
    ]);
    renderPersonality(per);
    renderAbilities(c.components || []);
    renderCalendar(cal);
  } catch (e) { if (e.message !== "locked") toast("Couldn't load settings."); }
}
$("#open-project").addEventListener("click", () => showView("project"));
$("#close-project").addEventListener("click", () => showView("settings"));

const ABILITY_NAMES = { memory: "Memory", web_search: "Web search", clock: "Date and time", reminders: "Reminders",
  calendar: "Calendar", research: "Project research" };
function renderAbilities(list) {
  const ul = $("#abilities");
  ul.innerHTML = "";
  for (const c of list) {
    const li = document.createElement("li");
    const text = document.createElement("div");
    text.append(Object.assign(document.createElement("div"), { className: "name", textContent: ABILITY_NAMES[c.name] || c.name }),
                Object.assign(document.createElement("div"), { className: "desc", textContent: c.description || "" }));
    const sw = Object.assign(document.createElement("button"), { className: "switch", type: "button" });
    sw.setAttribute("role", "switch");
    sw.setAttribute("aria-checked", String(c.enabled));
    sw.setAttribute("aria-label", ABILITY_NAMES[c.name] || c.name);
    sw.addEventListener("click", async () => {
      const on = sw.getAttribute("aria-checked") !== "true";
      if (c.name === "memory" && !on) {
        toast("Memory off: WOLF won't remember new things until you turn it back on. What it knows stays saved.", 5000);
      }
      sw.disabled = true;
      try {
        const res = await api("/api/components", { method: "POST", body: JSON.stringify({ name: c.name, enabled: on }) });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error);
        renderAbilities(data.components);
        if (c.name !== "memory" || on) toast(`${ABILITY_NAMES[c.name] || c.name} is ${on ? "on" : "off"} from your next conversation.`, 2500);
      } catch (e) { if (e.message !== "locked") toast("Couldn't change that. Try again."); sw.disabled = false; }
    });
    li.append(text, sw);
    ul.appendChild(li);
  }
}

/* ---------- personality ---------- */
function renderPersonality(data) {
  const form = $("#personality");
  form.innerHTML = "";
  const options = [...data.presets, { id: "custom", name: "Your own", summary: "Describe the personality you want, in your own words." }];
  for (const o of options) {
    const label = el("label", "choice");
    const radio = Object.assign(document.createElement("input"), { type: "radio", name: "personality", value: o.id, checked: o.id === data.current });
    const text = el("div");
    text.append(el("div", "name", o.name), el("div", "desc", o.summary));
    label.append(radio, text);
    form.append(label);
  }
  const custom = Object.assign(document.createElement("textarea"), { id: "personality-custom", rows: 4, maxLength: 4000,
    placeholder: "For example: \"Talk like a laid-back friend. Short sentences, a bit of humor, honest even when it stings.\"" });
  custom.value = data.custom || "";
  custom.setAttribute("aria-label", "Describe your own personality for WOLF");
  const box = el("div"); box.append(custom); box.hidden = data.current !== "custom";
  const actions = el("div", "form-actions");
  const save = Object.assign(el("button", "pill-btn primary", "Save personality"), { type: "submit" });
  actions.append(save);
  form.append(box, actions);
  form.onchange = () => { box.hidden = form.elements.personality.value !== "custom"; };
  form.onsubmit = async (e) => {
    e.preventDefault();
    const id = form.elements.personality.value;
    save.disabled = true;
    try {
      const res = await api("/api/personality", { method: "POST", body: JSON.stringify({ id, custom: id === "custom" ? custom.value : undefined }) });
      const out = await res.json();
      if (!res.ok) throw new Error(out.error);
      renderPersonality(out);
      toast("Saved. WOLF will sound like this from your next conversation.");
    } catch (err) { if (err.message !== "locked") toast(err.message || "Couldn't save that."); save.disabled = false; }
  };
}

/* ---------- reminders ---------- */
function whenText(iso) {
  const d = new Date(iso);
  return `${dayLabel(d)}, ${d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`;
}
async function markDone(id) {
  try {
    const res = await api(`/api/reminders/${encodeURIComponent(id)}/done`, { method: "POST", body: "{}" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    renderReminders(data);
    renderDue(data.due);
  } catch (e) { if (e.message !== "locked") toast("Couldn't update that reminder."); }
}
function renderReminders(data) {
  const ul = $("#reminders");
  ul.innerHTML = "";
  if (!data.open.length) ul.append(el("li", "muted", "No reminders. Try telling WOLF \"remind me to call Mom on Sunday\"."));
  const now = Date.now();
  for (const r of data.open) {
    const li = el("li", new Date(r.due).getTime() <= now ? "overdue" : "");
    const done = Object.assign(el("button", "small-btn", "Done"), { type: "button" });
    done.addEventListener("click", () => markDone(r.id));
    li.append(el("span", null, r.text), el("span", "when", whenText(r.due)), done);
    ul.append(li);
  }
}
function renderDue(due) {
  const box = $("#due-banner");
  box.innerHTML = "";
  box.hidden = !due.length;
  for (const r of due) {
    const row = el("div", "row");
    const text = el("span");
    text.append(el("b", null, "Reminder: "), document.createTextNode(`${r.text} (${whenText(r.due)})`));
    const done = Object.assign(el("button", "small-btn", "Done"), { type: "button" });
    done.addEventListener("click", () => markDone(r.id));
    row.append(text, done);
    box.append(row);
  }
}
async function checkDue() {
  if (!token()) return;
  try { renderDue((await (await api("/api/reminders")).json()).due); } catch { /* shown next time */ }
}
checkDue();
setInterval(() => { if (!document.hidden) checkDue(); }, 60000);
(function presetReminderTime() {
  const d = new Date(Date.now() + 60 * 60 * 1000);
  d.setMinutes(0, 0, 0);
  const pad = (n) => String(n).padStart(2, "0");
  $("#rm-due").value = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:00`;
})();
$("#reminder-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const data = await postForm("/api/reminders", { text: $("#rm-text").value, due: $("#rm-due").value }, e.target, false);
  if (!data) return;
  $("#rm-text").value = "";
  $("#add-reminder").open = false;
  renderReminders(data);
  renderDue(data.due);
  toast("Reminder added");
});

/* ---------- calendar ---------- */
function renderCalendar(data) {
  $("#cal-howto").textContent = data.how_to || "";
  const ul = $("#calendars");
  ul.innerHTML = "";
  for (const c of data.calendars) {
    const li = el("li");
    const remove = Object.assign(el("button", "small-btn", "Remove"), { type: "button" });
    remove.addEventListener("click", async () => {
      try {
        const res = await api(`/api/calendar/${encodeURIComponent(c.name)}`, { method: "DELETE" });
        if (!res.ok) throw new Error((await res.json()).error);
        renderCalendar(await res.json());
        toast(`${c.name} disconnected`);
      } catch (e) { if (e.message !== "locked") toast(e.message || "Couldn't remove it."); }
    });
    li.append(el("span", null, c.name), el("span", "when", c.source), remove);
    ul.append(li);
  }
  if (!data.calendars.length) ul.append(el("li", "muted", "No calendar connected yet."));
  const box = $("#cal-events");
  box.innerHTML = "";
  if (!data.calendars.length) {
    box.append(el("p", "hint", "Connect your calendar and your events will show up here, so WOLF can help plan around them."));
    const go = Object.assign(el("button", "pill-btn", "Connect a calendar"), { type: "button" });
    go.addEventListener("click", () => { showView("settings"); setTimeout(() => $("#cal-name").focus(), 50); });
    box.append(go);
    return;
  }
  if (data.error) { box.append(el("p", "hint", data.error)); return; }
  if (!data.events.length) box.append(el("p", "hint", "Nothing scheduled."));
  for (const ev of data.events.slice(0, 8)) {
    const row = el("div", "event");
    const when = ev.all_day ? `${dayLabel(ev.start)}, all day` : whenText(ev.start);
    row.append(el("span", null, ev.title), el("span", "when", when));
    box.append(row);
  }
}
$("#calendar-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const button = e.target.querySelector("[type=submit]");
  button.textContent = "Checking the link…";
  const data = await postForm("/api/calendar", { name: $("#cal-name").value, url: $("#cal-url").value }, e.target, false);
  button.textContent = "Connect calendar";
  if (!data) return;
  e.target.reset();
  renderCalendar(data);
  loadSettings();
  toast(`Connected. WOLF can now see ${data.added_events} events on that calendar.`);
});

/* ---------- project: build tracker, production plan, research forum ---------- */
let projectTimer = null;
let openThread = null;
let planItems = [];
const STATUS_LABEL = { done: "Done", active: "In progress", next: "Up next", later: "Later", idea: "Idea" };
const WHO_LABEL = { human: "Needs you", claude: "Claude", either: "Anyone" };

function stopProjectRefresh() { clearInterval(projectTimer); projectTimer = null; }
async function loadProject() {
  try {
    const data = await (await api("/api/hub")).json();
    $("#hub-missing").hidden = data.available;
    $("#hub").hidden = !data.available;
    if (!data.available) return;
    renderBuild(data.progress);
    renderPlan(data.plan);
    if (!openThread) renderThreads(data.threads);
  } catch (e) { if (e.message !== "locked") toast("Couldn't load the project hub."); }
  if (!projectTimer) projectTimer = setInterval(() => { if (!document.hidden) loadProject(); }, 20000);
}

function renderBuild(d) {
  if (!d) { $("#build-title").textContent = "Nothing in progress"; $("#build-now").textContent = ""; $("#build-pct").textContent = ""; return; }
  const pct = Math.max(0, Math.min(100, Math.round(Number(d.percent) || 0)));
  const done = d.status === "done" || pct >= 100;
  $("#build-title").textContent = d.title || "Current work";
  $("#build-pct").textContent = pct + "%";
  $("#build-meter").style.width = pct + "%";
  $("#build-now").textContent = (done ? "Finished" : (d.current || "In progress")) + (d.updated ? ` · updated ${ago(d.updated)}` : "");
}

function renderPlan(plan) {
  const s = plan.summary || { done: 0, items: 0, percent: 0 };
  $("#plan-count").textContent = `${s.done} of ${s.items} done`;
  $("#plan-meter").style.width = s.percent + "%";
  $("#plan-about").textContent = "Everything WOLF is and will be, in order. Items marked \"Needs you\" are waiting on a person.";
  const box = $("#plan");
  const open = new Set([...box.querySelectorAll("details[open]")].map((d) => d.dataset.id));
  const first = !box.children.length;
  box.innerHTML = "";
  planItems = [];
  for (const phase of plan.phases || []) {
    const items = phase.items || [];
    const det = el("details", "phase");
    det.dataset.id = phase.id;
    det.open = first ? ["active", "next"].includes(phase.status) : open.has(phase.id);
    const sum = el("summary");
    sum.append(el("span", "pname", phase.name), el("span", "count", `${items.filter((i) => i.status === "done").length}/${items.length}`),
               el("span", `pill ${phase.status}`, STATUS_LABEL[phase.status] || phase.status));
    det.append(sum);
    if (phase.goal) det.append(el("p", "goal", phase.goal));
    const ul = el("ul", "items");
    for (const item of items) {
      planItems.push(item);
      const li = el("li");
      const tags = el("span", "tags");
      if (item.who) tags.append(el("span", "who", WHO_LABEL[item.who] || item.who));
      tags.append(el("span", `pill ${item.status}`, STATUS_LABEL[item.status] || item.status));
      li.append(el("span", "title", item.title), tags);
      if (item.note) li.append(el("span", "note", item.note));
      ul.appendChild(li);
    }
    det.append(ul);
    box.appendChild(det);
  }
  const sel = $("#tf-topic");
  const current = sel.value;
  sel.innerHTML = '<option value="">None</option>';
  for (const i of planItems) sel.append(Object.assign(el("option", null, i.title), { value: i.id }));
  sel.value = current;
}

function kindPill(kind) { return el("span", `pill ${kind === "ai" ? "ai" : "human"}`, kind === "ai" ? "AI" : "Person"); }
function topicTitle(id) { return (planItems.find((i) => i.id === id) || {}).title || id; }

function renderThreads(list) {
  const ul = $("#threads");
  ul.innerHTML = "";
  if (!list.length) { ul.innerHTML = '<li class="muted">No threads yet. Start the first one.</li>'; return; }
  for (const t of list) {
    const b = el("button");
    b.type = "button";
    const meta = el("span", "t-meta");
    meta.append(kindPill(t.started_kind), el("span", null, `${t.started_by} · ${t.replies} ${t.replies === 1 ? "reply" : "replies"} · active ${ago(t.last_time)}`));
    if (t.topic) meta.append(el("span", "pill later", topicTitle(t.topic)));
    b.append(el("span", "t-title", t.title), meta, el("span", "t-preview", t.preview));
    b.addEventListener("click", () => showThread(t.id));
    const li = el("li"); li.append(b); ul.appendChild(li);
  }
}

async function showThread(id) {
  try {
    const res = await api(`/api/hub/forum/${encodeURIComponent(id)}`);
    const t = await res.json();
    if (!res.ok) throw new Error(t.error);
    openThread = id;
    $("#threads").hidden = true; $("#thread-form").hidden = true; $("#new-thread-btn").hidden = true;
    $("#thread-view").hidden = false;
    $("#thread-title").textContent = t.title;
    $("#thread-topic").textContent = t.topic ? `Plan item: ${topicTitle(t.topic)}` : "";
    const ol = $("#posts");
    ol.innerHTML = "";
    for (const p of t.posts) {
      const li = el("li", p.kind === "ai" ? "ai" : "human");
      const meta = el("div", "p-meta");
      meta.append(el("span", "p-author", p.author), kindPill(p.kind), el("span", null, ago(p.time)));
      const body = el("div", "p-body md"); body.innerHTML = md(p.body);
      li.append(meta, body);
      ol.appendChild(li);
    }
    $("#rf-author").value = store.get("wolf.author", "");
  } catch (e) { if (e.message !== "locked") toast(e.message || "Couldn't open that thread."); }
}
function closeThread() {
  openThread = null;
  $("#thread-view").hidden = true; $("#threads").hidden = false; $("#new-thread-btn").hidden = false;
  loadProject();
}
$("#thread-back").addEventListener("click", closeThread);
$("#new-thread-btn").addEventListener("click", () => {
  $("#thread-form").hidden = false;
  $("#tf-author").value = store.get("wolf.author", "");
  $("#tf-title").focus();
});
$("#tf-cancel").addEventListener("click", () => { $("#thread-form").hidden = true; });

async function postForm(url, payload, form, rememberAuthor = true) {
  const button = form.querySelector("[type=submit]");
  button.disabled = true;
  try {
    const res = await api(url, { method: "POST", body: JSON.stringify(payload) });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    if (rememberAuthor) store.set("wolf.author", payload.author);
    return data;
  } catch (e) { if (e.message !== "locked") toast(e.message || "Couldn't post that. Try again."); return null; }
  finally { button.disabled = false; }
}
$("#thread-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const t = await postForm("/api/hub/forum", { title: $("#tf-title").value, body: $("#tf-body").value,
    author: $("#tf-author").value, topic: $("#tf-topic").value }, e.target);
  if (!t) return;
  e.target.reset(); e.target.hidden = true;
  toast("Thread posted");
  showThread(t.id);
});
$("#reply-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const t = await postForm(`/api/hub/forum/${encodeURIComponent(openThread)}`,
    { body: $("#rf-body").value, author: $("#rf-author").value }, e.target);
  if (!t) return;
  $("#rf-body").value = "";
  showThread(t.id);
});

/* ---------- install / offline shell ---------- */
if ("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
