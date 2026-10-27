const $ = (id) => document.getElementById(id);
const statusPill = $("status-pill");
const chatWindow = $("chat-window");
const messageInput = $("message-input");
const voiceToggle = $("voice-toggle");
const voiceStatus = $("voice-status");
const speechToggle = $("speech-toggle");
const wakeToggle = $("wake-toggle");

const TOKEN_KEY = "jarvisApiToken";
const WAKE_WORDS = ["jarvis", "jarbas", "jarves", "javis"];
const CONVERSATION_MS = 25000;

let recognition = null;
let listening = false;
let conversationUntil = 0;
let lastMessageId = null;
let lastSpokenId = null;
let skills = [];
let canEditPermissions = true;
let confirmationOpen = false;

// ------------------------------------------------------------------ API
function token() {
  return sessionStorage.getItem(TOKEN_KEY) || "";
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (token()) headers.set("Authorization", `Bearer ${token()}`);
  if (options.body) headers.set("Content-Type", "application/json");
  const response = await fetch(path, { ...options, headers });
  if (response.status === 401 && !path.startsWith("/api/login")) {
    const body = await response.json().catch(() => ({}));
    sessionStorage.removeItem(TOKEN_KEY);
    await requestLogin(body.login === "token" ? "token" : "user");
    return api(path, options);
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Erro ${response.status}`);
  return data;
}

const apiGet = (path) => api(path);
const apiPost = (path, data) => api(path, { method: "POST", body: JSON.stringify(data) });

// ------------------------------------------------------------------ login
let loginPromise = null;

function requestLogin(kind) {
  if (loginPromise) return loginPromise;
  if (kind === "token") {
    const value = window.prompt("Token de acesso do JARVIS:") || "";
    if (value) sessionStorage.setItem(TOKEN_KEY, value);
    return Promise.resolve();
  }
  const dialog = $("login-dialog");
  loginPromise = new Promise((resolve) => {
    $("login-error").textContent = "";
    dialog.showModal();
    $("login-form").onsubmit = async (event) => {
      event.preventDefault();
      try {
        const res = await fetch("/api/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username: $("login-username").value, password: $("login-password").value }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Falha no login");
        sessionStorage.setItem(TOKEN_KEY, data.token);
        $("login-password").value = "";
        dialog.close();
        loginPromise = null;
        resolve();
      } catch (err) {
        $("login-error").textContent = err.message;
      }
    };
  });
  return loginPromise;
}

async function logout() {
  await apiPost("/api/logout", {}).catch(() => {});
  sessionStorage.removeItem(TOKEN_KEY);
  location.reload();
}

function showUser(user) {
  const chip = $("user-chip");
  chip.hidden = !user;
  $("logout").hidden = !user;
  if (user) chip.textContent = `${user.display_name}${user.role === "admin" ? " · admin" : ""}`;
}

// ------------------------------------------------------------------ conversa
function formatMessage(message) {
  const isJarvis = message.source === "jarvis";
  const wrapper = document.createElement("div");
  wrapper.className = `message ${isJarvis ? "jarvis" : "user"}`;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = message.text;
  const meta = document.createElement("span");
  meta.className = "meta";
  const origin = { web: "navegador", voice: "voz", terminal: "terminal", gui: "app" }[message.source] || message.source;
  meta.textContent = `${isJarvis ? "JARVIS" : `Você (${origin})`} • ${new Date(message.timestamp).toLocaleString()}`;
  wrapper.append(bubble, meta);
  return wrapper;
}

async function loadHistory() {
  try {
    const data = await apiGet("/api/history?limit=200");
    const messages = data.messages.slice().reverse();
    const newest = messages.length ? messages[messages.length - 1].id : null;
    if (newest === lastMessageId) return;
    lastMessageId = newest;
    chatWindow.replaceChildren(...messages.map(formatMessage));
    chatWindow.scrollTop = chatWindow.scrollHeight;

    const latestJarvis = messages.slice().reverse().find((m) => m.source === "jarvis");
    if (latestJarvis && lastSpokenId === null) {
      lastSpokenId = latestJarvis.id; // não lê o histórico antigo ao abrir a página
    } else if (latestJarvis && latestJarvis.id !== lastSpokenId) {
      lastSpokenId = latestJarvis.id;
      if (speechToggle.checked) speak(latestJarvis.text);
    }
  } catch (err) {
    setStatus("Falha ao carregar histórico", "danger");
    console.error(err);
  }
}

async function sendMessage(textOverride) {
  const text = (textOverride ?? messageInput.value).trim();
  if (!text) return;
  messageInput.value = "";
  setStatus("Pensando...", "accent");
  try {
    await apiPost("/api/message", { text });
    setStatus("Online", "success");
  } catch (err) {
    setStatus(err.message, "danger");
  } finally {
    await loadHistory();
  }
}

async function clearHistory() {
  try {
    await apiPost("/api/history/clear", {});
    lastMessageId = null;
    await loadHistory();
  } catch (err) {
    setStatus(err.message, "danger");
  }
}

// ------------------------------------------------------------------ confirmações
function pollConfirmations() {
  const tick = async () => {
    if (!confirmationOpen) {
      try {
        const data = await apiGet("/api/confirmations");
        if (data.pending.length) await askConfirmation(data.pending[0]);
      } catch (err) {
        console.error(err);
      }
    }
    setTimeout(tick, 800);
  };
  setTimeout(tick, 400);
}

function askConfirmation(item) {
  confirmationOpen = true;
  const dialog = $("confirm-dialog");
  $("confirm-text").textContent = item.description;
  if (speechToggle.checked) speak(`Confirma: ${item.description}?`);
  dialog.showModal();
  return new Promise((resolve) => {
    const answer = async (approved) => {
      dialog.close();
      confirmationOpen = false;
      await apiPost("/api/confirmations", { id: item.id, approved }).catch(() => {});
      resolve();
    };
    $("confirm-yes").onclick = () => answer(true);
    $("confirm-no").onclick = () => answer(false);
    dialog.oncancel = () => answer(false);
  });
}

// ------------------------------------------------------------------ painéis
async function loadStatus() {
  try {
    const data = await apiGet("/api/status");
    $("app-name").textContent = data.app.name;
    $("app-version").textContent = `v${data.app.version}`;
    $("ai-provider").textContent = {
      anthropic: "Claude (Anthropic)",
      openai: "OpenAI",
      gemini: "Google Gemini",
      offline: "offline — configure uma chave no .env",
    }[data.ai_provider] || data.ai_provider || "—";
    $("app-host").textContent = location.host;
    $("plugin-list").replaceChildren(
      ...data.plugins.map((plugin) => {
        const item = document.createElement("li");
        item.textContent = `${plugin.name} — ${plugin.description}`;
        return item;
      })
    );
    showUser(data.user);
    setStatus("Online", "success");
  } catch (err) {
    setStatus("Offline", "danger");
  }
}

async function loadSkills() {
  const data = await apiGet("/api/skills").catch(() => ({ skills: [] }));
  skills = data.skills;
  renderSkills();
}

function renderSkills() {
  const filter = $("skill-filter").value.toLowerCase();
  const list = $("skill-list");
  const items = skills
    .filter((s) => !filter || `${s.description} ${s.examples.join(" ")} ${s.category}`.toLowerCase().includes(filter))
    .map((skill) => {
      const item = document.createElement("button");
      item.className = "skill";
      item.title = "Clique para usar";
      const example = skill.examples[0] || "";
      item.innerHTML = `<span class="category"></span><strong></strong><small></small>`;
      item.querySelector(".category").textContent = skill.category;
      item.querySelector("strong").textContent = example ? `“${example}”` : skill.name;
      item.querySelector("small").textContent = skill.description;
      item.addEventListener("click", () => {
        messageInput.value = example;
        messageInput.focus();
      });
      return item;
    });
  list.replaceChildren(...items);
}

async function loadPermissions() {
  try {
    const data = await apiGet("/api/permissions");
    canEditPermissions = data.can_edit !== false;
    $("permissions-hint").textContent = canEditPermissions ? "" : "Somente administradores podem alterar.";
    $("save-permissions").hidden = !canEditPermissions;
    $("permissions-list").replaceChildren(
      ...data.permissions.map((perm) => {
        const row = document.createElement("label");
        row.className = "permission-row";
        const text = document.createElement("span");
        text.textContent = perm.description;
        text.title = perm.key;
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.checked = perm.allowed;
        checkbox.disabled = !canEditPermissions;
        checkbox.dataset.key = perm.key;
        row.append(text, checkbox);
        return row;
      })
    );
  } catch (err) {
    console.error(err);
  }
}

async function savePermissions() {
  const values = {};
  document.querySelectorAll(".permission-row input").forEach((checkbox) => {
    values[checkbox.dataset.key] = checkbox.checked;
  });
  try {
    await apiPost("/api/permissions", { permissions: values });
    setStatus("Permissões salvas", "accent");
  } catch (err) {
    setStatus(err.message, "danger");
  }
}

function setStatus(text, tone) {
  statusPill.textContent = text;
  statusPill.dataset.tone = tone;
}

// ------------------------------------------------------------------ voz
function speak(text) {
  if (!window.speechSynthesis) return;
  const utterance = new SpeechSynthesisUtterance(text.slice(0, 600));
  utterance.lang = "pt-BR";
  const voice = speechSynthesis.getVoices().find((v) => v.lang && v.lang.toLowerCase().startsWith("pt"));
  if (voice) utterance.voice = voice;
  speechSynthesis.cancel();
  speechSynthesis.speak(utterance);
}

function extractCommand(transcript) {
  const plain = transcript.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  for (const word of WAKE_WORDS) {
    const index = plain.search(new RegExp(`\\b${word}\\b`));
    if (index >= 0) return transcript.slice(index + word.length).replace(/^[\s,.:;!?-]+/, "");
  }
  return null;
}

function initVoice() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    voiceStatus.textContent = "Reconhecimento de voz não suportado neste navegador (use Chrome ou Edge).";
    voiceToggle.disabled = true;
    return;
  }
  recognition = new SpeechRecognition();
  recognition.lang = "pt-BR";
  recognition.interimResults = false;
  recognition.continuous = true;

  recognition.addEventListener("result", (event) => {
    const transcript = event.results[event.results.length - 1][0].transcript.trim();
    if (!transcript || (window.speechSynthesis && speechSynthesis.speaking)) return;
    let command = transcript;
    if (wakeToggle.checked && Date.now() > conversationUntil) {
      command = extractCommand(transcript);
      if (command === null) return;
      if (!command) {
        conversationUntil = Date.now() + CONVERSATION_MS;
        voiceStatus.textContent = "Pode falar...";
        return;
      }
    }
    conversationUntil = Date.now() + CONVERSATION_MS;
    sendMessage(command);
  });
  recognition.addEventListener("end", () => {
    if (listening) recognition.start();
  });
  recognition.addEventListener("error", (event) => {
    if (event.error === "no-speech") return;
    voiceStatus.textContent = `Erro no microfone: ${event.error}`;
    listening = false;
    updateVoiceUi();
  });
}

function toggleListening() {
  if (!recognition) return;
  listening = !listening;
  if (listening) recognition.start();
  else recognition.stop();
  updateVoiceUi();
}

function updateVoiceUi() {
  voiceToggle.classList.toggle("on", listening);
  voiceToggle.setAttribute("aria-label", listening ? "Desligar microfone" : "Ativar microfone");
  voiceStatus.textContent = listening
    ? wakeToggle.checked
      ? "Ouvindo — diga “Jarvis” e o pedido."
      : "Ouvindo — pode falar."
    : "Microfone desligado.";
}

// ------------------------------------------------------------------ início
function setupEventListeners() {
  $("send-message").addEventListener("click", () => sendMessage());
  $("refresh-history").addEventListener("click", () => {
    lastMessageId = null;
    loadHistory();
  });
  $("save-permissions").addEventListener("click", savePermissions);
  $("clear-history").addEventListener("click", clearHistory);
  $("logout").addEventListener("click", logout);
  $("skill-filter").addEventListener("input", renderSkills);
  voiceToggle.addEventListener("click", toggleListening);
  wakeToggle.addEventListener("change", updateVoiceUi);
  document.querySelectorAll(".action-btn").forEach((button) => {
    button.addEventListener("click", () => sendMessage(button.dataset.command));
  });
  messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  });
}

async function init() {
  setupEventListeners();
  initVoice();
  const auth = await fetch("/api/auth", { headers: token() ? { Authorization: `Bearer ${token()}` } : {} })
    .then((r) => r.json())
    .catch(() => ({}));
  if (auth.login_required && !auth.user) await requestLogin("user");
  await Promise.all([loadStatus(), loadPermissions(), loadSkills(), loadHistory()]);
  setInterval(loadHistory, 2500);
  pollConfirmations();
}

window.addEventListener("DOMContentLoaded", init);
