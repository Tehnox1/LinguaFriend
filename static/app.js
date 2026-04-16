const messagesEl = document.getElementById("messages");
const answerForm = document.getElementById("answerForm");
const answerInput = document.getElementById("answerInput");
const topMenuBtn = document.getElementById("topMenuBtn");
const menuOverlay = document.getElementById("menuOverlay");
const menuBackdrop = document.getElementById("menuBackdrop");
const closeMenuBtn = document.getElementById("closeMenuBtn");
const hintToggle = document.getElementById("hintToggle");
const leaderboardList = document.getElementById("leaderboardList");
const leaderboardOverlay = document.getElementById("leaderboardOverlay");
const leaderboardBackdrop = document.getElementById("leaderboardBackdrop");
const closeLeaderboardBtn = document.getElementById("closeLeaderboardBtn");
const openLeaderboardBtn = document.getElementById("openLeaderboardBtn");
const levelButtons = Array.from(document.querySelectorAll(".level-pill"));
const nextButton = document.getElementById("nextBtn");
const moreInfoButton = document.getElementById("moreInfoBtn");
const MAX_VISIBLE_MESSAGES = 80;
const API_BASE =
  (window.APP_CONFIG && typeof window.APP_CONFIG.apiBaseUrl === "string"
    ? window.APP_CONFIG.apiBaseUrl
    : "").replace(/\/$/, "");

let isSending = false;
let currentState = null;

function applyRuntimeMode() {
  const tg = window.Telegram && window.Telegram.WebApp;
  const ua = navigator.userAgent || "";
  const isTelegramWebView = Boolean(tg) || /Telegram/i.test(ua);
  const isMobile = window.matchMedia("(max-width: 699px)").matches;

  document.body.classList.toggle("tg-lite", isTelegramWebView && isMobile);
}

async function api(path, method = "GET", body = null) {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : null,
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.error || "API error");
  }
  return data;
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function randomBotDelay() {
  return 1000 + Math.floor(Math.random() * 1001);
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function renderLeaderboard(rows) {
  leaderboardList.innerHTML = "";
  if (!rows || rows.length === 0) {
    const empty = document.createElement("div");
    empty.className = "leaderboard-empty";
    empty.textContent = "No points yet";
    leaderboardList.appendChild(empty);
    return;
  }

  const table = document.createElement("div");
  table.className = "leaderboard-table";

  const header = document.createElement("div");
  header.className = "leaderboard-row leaderboard-header";
  header.innerHTML = `
    <span class="leaderboard-rank">Place</span>
    <span class="leaderboard-name">Nickname</span>
    <span class="leaderboard-score">Points</span>
  `;
  table.appendChild(header);

  rows.forEach((row, index) => {
    const item = document.createElement("div");
    item.className = "leaderboard-row";
    item.innerHTML = `
      <span class="leaderboard-rank">${index + 1}</span>
      <span class="leaderboard-name">${row.display_name}</span>
      <span class="leaderboard-score">${row.score}</span>
    `;
    table.appendChild(item);
  });

  leaderboardList.appendChild(table);
}

function syncMenuState(state) {
  if (!state) return;

  const hintsEnabled = Boolean(state.hints_enabled);
  hintToggle.classList.toggle("off", !hintsEnabled);
  hintToggle.setAttribute("aria-pressed", hintsEnabled ? "true" : "false");

  const currentLevel = state.level || "A2";
  for (const button of levelButtons) {
    button.classList.toggle("active", button.dataset.level === currentLevel);
  }

  renderLeaderboard(state.leaderboard || []);
}

function render(state) {
  currentState = state;
  messagesEl.innerHTML = "";
  const history = (state.history || []).slice(-MAX_VISIBLE_MESSAGES);

  for (const item of history) {
    const div = document.createElement("div");
    div.className = `msg ${item.role}`;
    div.dataset.role = item.role === "user" ? "You" : "LinguaFriend";
    div.textContent = item.text;
    messagesEl.appendChild(div);
  }

  syncMenuState(state);
  scrollToBottom();
}

function addTempMessage(role, text, extraClass = "") {
  const div = document.createElement("div");
  div.className = `msg ${role} ${extraClass}`.trim();
  div.dataset.role = role === "user" ? "You" : "LinguaFriend";
  div.textContent = text;
  messagesEl.appendChild(div);
  scrollToBottom();
  return div;
}

function addTypingIndicator() {
  const div = document.createElement("div");
  div.className = "msg bot typing";
  div.dataset.role = "LinguaFriend";
  div.innerHTML = "<span></span><span></span><span></span>";
  messagesEl.appendChild(div);
  scrollToBottom();
  return div;
}

function openMenu() {
  menuOverlay.hidden = false;
}

function closeMenu() {
  menuOverlay.hidden = true;
}

function openLeaderboard() {
  leaderboardOverlay.hidden = false;
}

function closeLeaderboard() {
  leaderboardOverlay.hidden = true;
}

async function syncTelegramProfile() {
  const tg = window.Telegram && window.Telegram.WebApp;
  const user = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
  if (!user) return;

  await api("/api/profile", "POST", {
    telegram_user_id: user.id,
    username: user.username || "",
    first_name: user.first_name || "",
    last_name: user.last_name || "",
  });
}

async function refresh() {
  try {
    const state = await api("/api/state");
    render(state);
  } catch {
    render({
      level: null,
      hints_enabled: true,
      history: [
        {
          role: "bot",
          text:
            "Сайт открыт, но API недоступно.\n\nДля GitHub Pages укажите адрес бэкенда в docs/config.js.",
        },
      ],
      leaderboard: [],
    });
  }
}

async function simulateBotReply(path, body = null, userEchoText = "") {
  if (isSending) return;
  isSending = true;

  const originalDisabled = answerInput.disabled;
  answerInput.disabled = true;

  let tempUser = null;
  if (userEchoText) {
    tempUser = addTempMessage("user", userEchoText, "sending");
  }

  const typing = addTypingIndicator();

  try {
    await delay(randomBotDelay());
    const state = await api(path, "POST", body);
    render(state);
  } catch {
    addTempMessage("bot", "Ошибка отправки. Попробуй еще раз.");
  } finally {
    if (tempUser && tempUser.parentNode) tempUser.remove();
    if (typing.parentNode) typing.remove();
    answerInput.disabled = originalDisabled;
    answerInput.focus();
    isSending = false;
  }
}

nextButton.addEventListener("click", () => simulateBotReply("/api/next", null, "Следующее предложение"));
moreInfoButton.addEventListener("click", () => simulateBotReply("/api/more-info", null, "Больше информации"));

topMenuBtn.addEventListener("click", () => {
  if (menuOverlay.hidden) {
    openMenu();
  } else {
    closeMenu();
  }
});

openLeaderboardBtn.addEventListener("click", openLeaderboard);
closeLeaderboardBtn.addEventListener("click", closeLeaderboard);
leaderboardBackdrop.addEventListener("click", closeLeaderboard);
closeMenuBtn.addEventListener("click", closeMenu);
menuBackdrop.addEventListener("click", closeMenu);

hintToggle.addEventListener("click", async () => {
  if (isSending || !currentState) return;
  const nextEnabled = !Boolean(currentState.hints_enabled);
  const state = await api("/api/set-hints", "POST", { enabled: nextEnabled });
  render(state);
});

for (const button of levelButtons) {
  button.addEventListener("click", async () => {
    if (isSending) return;
    const state = await api("/api/set-level", "POST", { level: button.dataset.level });
    render(state);
  });
}

answerForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = answerInput.value.trim();
  if (!text || isSending) return;

  answerInput.value = "";
  await simulateBotReply("/api/answer", { text }, text);
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (!leaderboardOverlay.hidden) {
      closeLeaderboard();
      return;
    }
    if (!menuOverlay.hidden) {
      closeMenu();
    }
  }
});

(async () => {
  applyRuntimeMode();
  await syncTelegramProfile();
  await refresh();
})();

