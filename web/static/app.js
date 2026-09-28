const statusPill = document.getElementById("status-pill");
const chatWindow = document.getElementById("chat-window");
const messageInput = document.getElementById("message-input");
const permissionsList = document.getElementById("permissions-list");
const pluginList = document.getElementById("plugin-list");
const appName = document.getElementById("app-name");
const appVersion = document.getElementById("app-version");

const host = location.hostname || "127.0.0.1";
const port = location.port || "8000";
const voiceToggle = document.getElementById("voice-toggle");
const speechToggle = document.getElementById("speech-toggle");
const voiceStatus = document.getElementById("voice-status");

let voiceRecognition = null;
let listening = false;
let voiceResponseEnabled = true;
let lastSpokenId = null;

function apiUrl(path) {
  return `${path}`;
}

async function authorizedFetch(path, options = {}) {
  const headers = new Headers(options.headers || {});
  let token = sessionStorage.getItem("jarvisApiToken") || "";

  for (let attempt = 0; attempt < 2; attempt += 1) {
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const response = await fetch(apiUrl(path), { ...options, headers });
    if (response.status !== 401 || attempt > 0) {
      if (response.status === 401) sessionStorage.removeItem("jarvisApiToken");
      return response;
    }

    token = window.prompt("Token de acesso do JARVIS:") || "";
    if (!token) return response;
    sessionStorage.setItem("jarvisApiToken", token);
  }
}

async function apiGet(path) {
  const res = await authorizedFetch(path);
  if (!res.ok) throw new Error(`Erro ${res.status}`);
  return res.json();
}

async function apiPost(path, data) {
  const res = await authorizedFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Erro ${res.status}: ${body}`);
  }
  return res.json();
}

function formatMessage(message) {
  const classes = ["message", message.source === "web" ? "user" : "jarvis"].join(" ");
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = message.text;

  const meta = document.createElement("span");
  meta.className = "meta";
  const source = message.source === "web" ? "Você" : message.source === "jarvis" ? "Jarvis" : message.source || "Sistema";
  meta.textContent = `${source} • ${new Date(message.timestamp).toLocaleString()}`;

  const wrapper = document.createElement("div");
  wrapper.className = classes;
  wrapper.appendChild(bubble);
  wrapper.appendChild(meta);
  return wrapper;
}

async function loadHistory() {
  try {
    const data = await apiGet("/api/history?limit=200");
    chatWindow.innerHTML = "";
    const messages = data.messages.slice().reverse();
    messages.forEach((message) => {
      chatWindow.appendChild(formatMessage(message));
    });
    chatWindow.scrollTop = chatWindow.scrollHeight;

    const latestJarvis = messages.slice().reverse().find((message) => message.source === "jarvis");
    if (voiceResponseEnabled && latestJarvis && latestJarvis.id !== lastSpokenId) {
      speakText(latestJarvis.text);
      lastSpokenId = latestJarvis.id;
    }
  } catch (err) {
    statusPill.textContent = "Falha ao carregar histórico";
    statusPill.style.background = "var(--danger)";
    console.error(err);
  }
}

async function loadPermissions() {
  try {
    const data = await apiGet("/api/permissions");
    permissionsList.innerHTML = "";
    data.permissions.forEach((perm) => {
      const row = document.createElement("div");
      row.className = "permission-row";

      const label = document.createElement("label");
      label.textContent = `${perm.key}: ${perm.description}`;

      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = perm.allowed;
      checkbox.dataset.key = perm.key;

      row.appendChild(label);
      row.appendChild(checkbox);
      permissionsList.appendChild(row);
    });
  } catch (err) {
    console.error(err);
  }
}

async function loadStatus() {
  try {
    const data = await apiGet("/api/status");
    appName.textContent = data.app.name;
    appVersion.textContent = data.app.version;
    pluginList.innerHTML = "";
    data.plugins.forEach((plugin) => {
      const item = document.createElement("li");
      item.textContent = `${plugin.name} — ${plugin.description}`;
      pluginList.appendChild(item);
    });
    statusPill.textContent = "Online";
    statusPill.style.background = "var(--success)";
  } catch (err) {
    statusPill.textContent = "Offline";
    statusPill.style.background = "var(--danger)";
  }
}

async function sendMessage() {
  const text = messageInput.value.trim();
  if (!text) return;
  try {
    await apiPost("/api/message", { text });
    messageInput.value = "";
    await loadHistory();
    if (voiceResponseEnabled) {
      await speakLatestJarvisResponse();
    }
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
    statusPill.textContent = "Permissões atualizadas";
    statusPill.style.background = "var(--accent-strong)";
  } catch (err) {
    console.error(err);
  }
}

function updateVoiceStatus() {
  const micStatus = listening ? "atividade de voz ativa" : "microfone desligado";
  const speechStatus = voiceResponseEnabled ? "resposta por voz ativada" : "resposta por voz desativada";
  voiceStatus.textContent = `${micStatus}. ${speechStatus}.`;
  if (listening) {
    voiceStatus.style.color = "#34d399";
  } else if (voiceResponseEnabled) {
    voiceStatus.style.color = "#38bdf8";
  } else {
    voiceStatus.style.color = "var(--muted)";
  }
}

function speakText(text) {
  if (!window.speechSynthesis) {
    return;
  }
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "pt-BR";
  utterance.rate = 1.0;
  utterance.pitch = 1.0;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utterance);
}

function initVoiceRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    voiceStatus.textContent = "Reconhecimento de voz não suportado neste navegador.";
    voiceToggle.disabled = true;
    return;
  }
  voiceRecognition = new SpeechRecognition();
  voiceRecognition.lang = "pt-BR";
  voiceRecognition.interimResults = false;
  voiceRecognition.maxAlternatives = 1;
  voiceRecognition.continuous = true;

  voiceRecognition.addEventListener("result", (event) => {
    const transcript = event.results[event.results.length - 1][0].transcript;
    messageInput.value = transcript;
    sendMessage();
  });

  voiceRecognition.addEventListener("end", () => {
    if (listening) {
      voiceRecognition.start();
    }
  });

  voiceRecognition.addEventListener("error", (event) => {
    console.error("Speech recognition error", event.error);
    listening = false;
    updateVoiceStatus();
  });
}

function toggleListening() {
  if (!voiceRecognition) {
    return;
  }
  listening = !listening;
  if (listening) {
    voiceRecognition.start();
    voiceToggle.textContent = "Parar microfone";
  } else {
    voiceRecognition.stop();
    voiceToggle.textContent = "Ativar microfone";
  }
  updateVoiceStatus();
}

function toggleSpeechResponse() {
  voiceResponseEnabled = !voiceResponseEnabled;
  speechToggle.textContent = voiceResponseEnabled ? "Desativar voz" : "Responder por voz";
  updateVoiceStatus();
}

async function speakLatestJarvisResponse() {
  try {
    const data = await apiGet("/api/history?limit=20");
    const messages = data.messages.slice().reverse();
    const latestJarvis = messages.reverse().find((message) => message.source === "jarvis");
    if (latestJarvis && latestJarvis.id !== lastSpokenId) {
      speakText(latestJarvis.text);
      lastSpokenId = latestJarvis.id;
    }
  } catch (err) {
    console.error("Falha ao falar a resposta mais recente:", err);
  }
}

async function clearHistory() {
  if (!confirm("Tem certeza que deseja limpar todo o histórico?")) return;
  try {
    await apiPost("/api/history/clear", {});
    loadHistory();
  } catch (err) {
    console.error(err);
  }
}

function setupEventListeners() {
  document.getElementById("send-message").addEventListener("click", sendMessage);
  document.getElementById("refresh-history").addEventListener("click", loadHistory);
  document.getElementById("save-permissions").addEventListener("click", savePermissions);
  document.getElementById("clear-history").addEventListener("click", clearHistory);
  voiceToggle.addEventListener("click", toggleListening);
  speechToggle.addEventListener("click", toggleSpeechResponse);
  document.querySelectorAll(".action-btn").forEach((button) => {
    button.addEventListener("click", () => {
      messageInput.value = button.dataset.command;
      messageInput.focus();
    });
  });
  messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  });
}

async function init() {
  document.getElementById("app-host").textContent = host;
  document.getElementById("app-port").textContent = port;
  setupEventListeners();
  initVoiceRecognition();
  updateVoiceStatus();
  await Promise.all([loadStatus(), loadPermissions(), loadHistory()]);
  setInterval(loadHistory, 3000);
}

window.addEventListener("DOMContentLoaded", init);
