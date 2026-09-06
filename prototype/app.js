const app = document.querySelector("#app");
const canvas = document.querySelector("#world-canvas");
const context = canvas.getContext("2d", { alpha: false });
const lobby = document.querySelector("#lobby");
const hud = document.querySelector("#hud");
const hotbar = document.querySelector("#hotbar");
const crosshair = document.querySelector("#crosshair");
const targetCard = document.querySelector("#target-card");
const overlay = document.querySelector("#overlay");
const overlayTitle = document.querySelector("#overlay-title");
const overlayKicker = document.querySelector("#overlay-kicker");
const overlayBody = document.querySelector("#overlay-body");
const chat = document.querySelector("#chat");
const toast = document.querySelector("#toast");
const regionLabel = document.querySelector("#region-label");
const coordinateLabel = document.querySelector("#coordinate-label");
const targetCoordinate = document.querySelector("#target-coordinate");
const undoButton = document.querySelector("#undo-button");
const micIndicator = document.querySelector("#mic-indicator");
const agentIndicator = document.querySelector("#agent-indicator");

const state = {
  mode: "lobby",
  overlay: "none",
  player: { x: 0, z: 0, heading: 0 },
  target: { x: 12, z: 8 },
  keys: new Set(),
  lastFrame: performance.now(),
  pointerDown: false,
  pointerX: 0,
  preview: null,
  committed: [],
  history: [],
  selectedPlan: 0,
  microphone: false,
  agentConnected: false,
  agentListening: false,
  voiceMode: "spatial",
  structures: [
    { id: "lighthouse", kind: "tower", x: 22, z: -10, size: 7, height: 24, color: "#e8e1cd" },
    { id: "harbor-house", kind: "house", x: -12, z: 18, size: 8, height: 8, color: "#dba770" },
    { id: "gallery", kind: "house", x: 18, z: 22, size: 12, height: 7, color: "#8db9b4" },
  ],
  people: [
    { id: "mika", name: "Mika", x: 8, z: 5, color: "#ffbf69", activity: "港を案内しています" },
    { id: "sora", name: "Sora", x: -8, z: 9, color: "#9bd6ff", activity: "小さな家を制作中" },
    { id: "ren", name: "Ren", x: 14, z: -7, color: "#d3a6ff", activity: "灯台を見ています" },
  ],
};

function clamp(value, minimum, maximum) {
  return Math.min(maximum, Math.max(minimum, value));
}

function resize() {
  const ratio = Math.min(devicePixelRatio || 1, 2);
  canvas.width = Math.round(innerWidth * ratio);
  canvas.height = Math.round(innerHeight * ratio);
  canvas.style.width = `${innerWidth}px`;
  canvas.style.height = `${innerHeight}px`;
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
}

function worldToScreen(x, z, y = 0) {
  const scale = state.mode === "lobby" ? 12 : 16;
  const relativeX = x - state.player.x;
  const relativeZ = z - state.player.z;
  const cosine = Math.cos(-state.player.heading);
  const sine = Math.sin(-state.player.heading);
  const rotatedX = relativeX * cosine - relativeZ * sine;
  const rotatedZ = relativeX * sine + relativeZ * cosine;
  return {
    x: innerWidth / 2 + (rotatedX - rotatedZ) * scale,
    y: innerHeight * 0.54 + (rotatedX + rotatedZ) * scale * 0.46 - y * scale,
    depth: rotatedX + rotatedZ,
    scale,
  };
}

function screenToWorld(screenX, screenY) {
  const scale = state.mode === "lobby" ? 12 : 16;
  const isoX = (screenX - innerWidth / 2) / scale;
  const isoY = (screenY - innerHeight * 0.54) / (scale * 0.46);
  const rotatedX = (isoX + isoY) / 2;
  const rotatedZ = (isoY - isoX) / 2;
  const cosine = Math.cos(state.player.heading);
  const sine = Math.sin(state.player.heading);
  return {
    x: state.player.x + rotatedX * cosine - rotatedZ * sine,
    z: state.player.z + rotatedX * sine + rotatedZ * cosine,
  };
}

function terrainHeight(x, z) {
  const island = Math.max(0, 1 - Math.hypot(x, z) / 95);
  return island * (1.1 + Math.sin(x * 0.08) * 0.45 + Math.cos(z * 0.07) * 0.38);
}

function drawBackground() {
  const gradient = context.createLinearGradient(0, 0, 0, innerHeight);
  gradient.addColorStop(0, "#86bad0");
  gradient.addColorStop(0.48, "#bfd9d7");
  gradient.addColorStop(0.49, "#285e70");
  gradient.addColorStop(1, "#0b2531");
  context.fillStyle = gradient;
  context.fillRect(0, 0, innerWidth, innerHeight);
  context.fillStyle = "rgba(255,248,211,.75)";
  context.beginPath();
  context.arc(innerWidth * 0.76, innerHeight * 0.18, 38, 0, Math.PI * 2);
  context.fill();
}

function drawGround() {
  const cell = 8;
  const radius = state.mode === "lobby" ? 64 : 48;
  const cells = [];
  for (let x = Math.floor(state.player.x / cell) * cell - radius; x <= state.player.x + radius; x += cell) {
    for (let z = Math.floor(state.player.z / cell) * cell - radius; z <= state.player.z + radius; z += cell) {
      const distance = Math.hypot(x, z);
      if (distance > 102) continue;
      const y = terrainHeight(x + cell / 2, z + cell / 2);
      cells.push({ x, z, y, depth: worldToScreen(x, z, y).depth });
    }
  }
  cells.sort((a, b) => a.depth - b.depth);
  for (const cellData of cells) {
    const { x, z, y } = cellData;
    const points = [
      worldToScreen(x, z, y),
      worldToScreen(x + cell, z, terrainHeight(x + cell, z)),
      worldToScreen(x + cell, z + cell, terrainHeight(x + cell, z + cell)),
      worldToScreen(x, z + cell, terrainHeight(x, z + cell)),
    ];
    const distance = Math.hypot(x + cell / 2, z + cell / 2);
    const shore = distance > 82;
    const hue = shore ? "#cdbd86" : ((Math.floor(x / cell) + Math.floor(z / cell)) % 2 ? "#4e936a" : "#579f72");
    context.fillStyle = hue;
    context.strokeStyle = "rgba(20,55,42,.16)";
    context.lineWidth = 1;
    context.beginPath();
    context.moveTo(points[0].x, points[0].y);
    for (const point of points.slice(1)) context.lineTo(point.x, point.y);
    context.closePath();
    context.fill();
    context.stroke();
  }
}

function drawPrism(item, ghost = false) {
  const base = worldToScreen(item.x, item.z, terrainHeight(item.x, item.z));
  const scale = base.scale;
  const width = item.size * scale;
  const half = width / 2;
  const height = item.height * scale;
  const alpha = ghost ? 0.38 : 1;
  context.save();
  context.globalAlpha = alpha;
  context.translate(base.x, base.y);
  context.fillStyle = item.color;
  context.strokeStyle = ghost ? "#91ffd0" : "rgba(0,0,0,.26)";
  context.lineWidth = ghost ? 2.5 : 1;
  context.beginPath();
  context.moveTo(0, -height - half * .45);
  context.lineTo(half, -height);
  context.lineTo(0, -height + half * .45);
  context.lineTo(-half, -height);
  context.closePath();
  context.fill();
  context.stroke();
  context.fillStyle = ghost ? "#6cf4b4" : shade(item.color, -22);
  context.beginPath();
  context.moveTo(-half, -height);
  context.lineTo(0, -height + half * .45);
  context.lineTo(0, half * .45);
  context.lineTo(-half, 0);
  context.closePath();
  context.fill();
  context.stroke();
  context.fillStyle = ghost ? "#9fffd7" : shade(item.color, 18);
  context.beginPath();
  context.moveTo(half, -height);
  context.lineTo(0, -height + half * .45);
  context.lineTo(0, half * .45);
  context.lineTo(half, 0);
  context.closePath();
  context.fill();
  context.stroke();
  if (item.kind === "house") {
    context.fillStyle = ghost ? "#a8ffe0" : "#6b4434";
    context.beginPath();
    context.moveTo(-half * 1.15, -height);
    context.lineTo(0, -height - half * .9);
    context.lineTo(half * 1.15, -height);
    context.lineTo(0, -height + half * .56);
    context.closePath();
    context.fill();
    context.stroke();
  }
  context.restore();
}

function shade(hex, amount) {
  const value = hex.replace("#", "");
  const number = Number.parseInt(value, 16);
  const red = clamp((number >> 16) + amount, 0, 255);
  const green = clamp(((number >> 8) & 255) + amount, 0, 255);
  const blue = clamp((number & 255) + amount, 0, 255);
  return `rgb(${red},${green},${blue})`;
}

function drawPerson(person, isSelf = false) {
  const y = terrainHeight(person.x, person.z);
  const point = worldToScreen(person.x, person.z, y);
  const size = point.scale * .45;
  context.save();
  context.translate(point.x, point.y);
  context.fillStyle = isSelf ? "#7df0ba" : person.color;
  context.strokeStyle = "rgba(0,0,0,.45)";
  context.lineWidth = 2;
  context.beginPath();
  context.arc(0, -size * 3.1, size * .7, 0, Math.PI * 2);
  context.fill();
  context.stroke();
  context.fillRect(-size * .55, -size * 2.5, size * 1.1, size * 1.8);
  context.fillStyle = "rgba(5,15,20,.84)";
  context.font = "600 12px system-ui";
  context.textAlign = "center";
  context.fillText(isSelf ? "自分" : person.name, 0, -size * 4.4);
  context.restore();
}

function drawTarget() {
  if (state.mode !== "world") return;
  const point = worldToScreen(state.target.x, state.target.z, terrainHeight(state.target.x, state.target.z));
  context.save();
  context.strokeStyle = "rgba(143,255,205,.9)";
  context.lineWidth = 2;
  context.beginPath();
  context.ellipse(point.x, point.y, 22, 10, 0, 0, Math.PI * 2);
  context.stroke();
  context.restore();
}

function render(now) {
  const delta = Math.min((now - state.lastFrame) / 1000, 0.05);
  state.lastFrame = now;
  update(delta);
  drawBackground();
  drawGround();
  const items = [...state.structures, ...state.committed].sort((a, b) => worldToScreen(a.x, a.z).depth - worldToScreen(b.x, b.z).depth);
  for (const item of items) drawPrism(item);
  for (const person of [...state.people].sort((a, b) => worldToScreen(a.x, a.z).depth - worldToScreen(b.x, b.z).depth)) drawPerson(person);
  if (state.mode === "world") drawPerson({ ...state.player, color: "#7df0ba" }, true);
  if (state.preview) for (const item of state.preview.items) drawPrism(item, true);
  drawTarget();
  requestAnimationFrame(render);
}

function update(delta) {
  if (state.mode !== "world" || state.overlay !== "none" || !chat.hidden) return;
  const speed = state.keys.has("shift") ? 18 : 9;
  let forward = 0;
  let sideways = 0;
  if (state.keys.has("w")) forward += 1;
  if (state.keys.has("s")) forward -= 1;
  if (state.keys.has("d")) sideways += 1;
  if (state.keys.has("a")) sideways -= 1;
  if (!forward && !sideways) return;
  const length = Math.hypot(forward, sideways) || 1;
  forward /= length;
  sideways /= length;
  const cosine = Math.cos(state.player.heading);
  const sine = Math.sin(state.player.heading);
  state.player.x += (sideways * cosine + forward * sine) * speed * delta;
  state.player.z += (sideways * -sine + forward * cosine) * speed * delta;
  state.player.x = clamp(state.player.x, -82, 82);
  state.player.z = clamp(state.player.z, -82, 82);
  updateLocation();
}

function updateLocation() {
  const x = Math.round(state.player.x);
  const z = Math.round(state.player.z);
  const region = z < -18 ? "北の森" : x > 18 ? "灯台岬" : x < -18 ? "工房区" : z > 18 ? "港" : "港の丘";
  regionLabel.textContent = region;
  coordinateLabel.textContent = `X ${x} · Z ${z}`;
  targetCoordinate.textContent = `X ${Math.round(state.target.x)} · Z ${Math.round(state.target.z)}`;
}

function setMode(mode) {
  state.mode = mode;
  app.dataset.mode = mode;
  const inWorld = mode === "world";
  lobby.hidden = inWorld;
  hud.hidden = !inWorld;
  hotbar.hidden = !inWorld;
  crosshair.hidden = !inWorld;
  targetCard.hidden = !inWorld;
  if (inWorld) canvas.focus();
}

function showToast(message) {
  toast.textContent = message;
  toast.hidden = false;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => { toast.hidden = true; }, 2600);
}

function closeOverlay() {
  state.overlay = "none";
  app.dataset.overlay = "none";
  overlay.hidden = true;
  overlayBody.replaceChildren();
  if (state.mode === "world") canvas.focus();
}

function openOverlay(name) {
  state.overlay = name;
  app.dataset.overlay = name;
  overlay.hidden = false;
  const renderers = {
    build: renderBuild,
    agent: renderAgent,
    social: renderSocial,
    voice: renderVoice,
    map: renderMap,
    avatar: renderAvatar,
    invite: renderInvite,
    settings: renderSettings,
    pause: renderPause,
  };
  (renderers[name] || renderSettings)();
  overlay.querySelector("button, input, textarea, select")?.focus();
}

function setOverlayHeading(kicker, title) {
  overlayKicker.textContent = kicker;
  overlayTitle.textContent = title;
}

function renderBuild() {
  setOverlayHeading("AI Creative Mode", "見ている場所につくる");
  overlayBody.innerHTML = `
    <div class="panel-grid">
      <div class="card"><div class="status-line"><span>対象 X ${Math.round(state.target.x)} Z ${Math.round(state.target.z)}</span><span>近くの作品を保護</span><span>Previewのみ</span></div></div>
      <div class="card"><label for="build-intent"><strong>何を作りますか？</strong></label><textarea id="build-intent">ここに海を見渡せる小さな灯台を作って。既存の道につないで。</textarea><div class="action-row"><button class="primary" id="make-plans">3つの案をつくる</button><button class="secondary" data-example="trees">木を12本</button><button class="secondary" data-example="path">港まで道</button></div></div>
      <div id="plans"></div>
    </div>`;
  overlayBody.querySelector("#make-plans").addEventListener("click", createPlans);
  overlayBody.querySelector('[data-example="trees"]').addEventListener("click", () => { overlayBody.querySelector("#build-intent").value = "この辺に木を12本植えて。海への眺めは残して。"; });
  overlayBody.querySelector('[data-example="path"]').addEventListener("click", () => { overlayBody.querySelector("#build-intent").value = "ここから港まで歩きやすい石畳の道を作って。"; });
}

function createPlans() {
  const intent = overlayBody.querySelector("#build-intent").value.trim();
  if (!intent) return showToast("作りたいものを入力してください");
  state.selectedPlan = 0;
  const variants = [
    { name: "周囲になじむ案", size: 4, height: 15, count: 1, cost: 64, risk: "低" },
    { name: "コンパクト案", size: 3, height: 11, count: 1, cost: 42, risk: "低" },
    { name: "ランドマーク案", size: 5, height: 22, count: 1, cost: 105, risk: "中" },
  ];
  const plans = overlayBody.querySelector("#plans");
  plans.innerHTML = `<div class="card"><h3>施工案</h3><p>世界はまだ変更されていません。案を選んでGhostを確認します。</p><div class="plan-list">${variants.map((variant, index) => `<button class="plan" data-index="${index}" data-selected="${index === 0}"><span><strong>${variant.name}</strong><br><small>${variant.size}m幅 · ${variant.height}m高 · 削除0</small></span><span>${variant.cost} units · ${variant.risk}</span></button>`).join("")}</div><div class="action-row"><button class="primary" id="show-ghost">Ghostで確認</button></div></div>`;
  for (const button of plans.querySelectorAll(".plan")) {
    button.addEventListener("click", () => {
      state.selectedPlan = Number(button.dataset.index);
      for (const sibling of plans.querySelectorAll(".plan")) sibling.dataset.selected = String(sibling === button);
    });
  }
  plans.querySelector("#show-ghost").addEventListener("click", () => showGhost(variants[state.selectedPlan], intent));
}

function showGhost(variant, intent) {
  state.preview = {
    id: crypto.randomUUID(),
    intent,
    variant,
    items: [{ id: `preview-${Date.now()}`, kind: "tower", x: state.target.x, z: state.target.z, size: variant.size, height: variant.height, color: "#70e5ad" }],
  };
  setOverlayHeading("Ghost Preview", variant.name);
  overlayBody.innerHTML = `
    <div class="panel-grid">
      <div class="card"><h3>まだ世界は変わっていません</h3><p>半透明の建物、影響範囲、AIの仮定を確認してください。</p></div>
      <div class="card"><div class="status-line"><span>作成 ${variant.count}</span><span>変更 0</span><span>削除 0</span><span>費用 ${variant.cost}</span><span>リスク ${variant.risk}</span></div></div>
      <div class="card"><h3>AIの仮定</h3><p>既存の道と海への眺めを残し、他の人が所有する作品へ触れません。</p></div>
      <div class="action-row"><button class="primary" id="commit-preview">この計画で世界につくる</button><button class="secondary" id="revise-preview">案を選び直す</button><button class="danger" id="cancel-preview">取り消す</button></div>
    </div>`;
  overlayBody.querySelector("#commit-preview").addEventListener("click", commitPreview);
  overlayBody.querySelector("#revise-preview").addEventListener("click", renderBuild);
  overlayBody.querySelector("#cancel-preview").addEventListener("click", () => { state.preview = null; closeOverlay(); showToast("施工案を破棄しました"); });
}

function commitPreview() {
  if (!state.preview) return;
  const transaction = { id: crypto.randomUUID(), title: state.preview.intent, items: state.preview.items.map((item) => ({ ...item, id: crypto.randomUUID(), color: "#e5ddca" })) };
  state.committed.push(...transaction.items);
  state.history.push(transaction);
  state.preview = null;
  undoButton.disabled = false;
  closeOverlay();
  showToast("施工を1つのTransactionとして確定しました");
}

function undoLast() {
  const transaction = state.history.pop();
  if (!transaction) return;
  const ids = new Set(transaction.items.map((item) => item.id));
  state.committed = state.committed.filter((item) => !ids.has(item.id));
  undoButton.disabled = state.history.length === 0;
  showToast(`「${transaction.title.slice(0, 24)}」を戻しました`);
}

function renderAgent() {
  setOverlayHeading("Personal Agent", state.agentConnected ? "自分のAgent" : "Agentを接続");
  overlayBody.innerHTML = state.agentConnected ? `
    <div class="panel-grid">
      <div class="card"><div class="status-line"><span>CONNECTED</span><span>${state.agentListening ? "LISTENING" : "VOICE OFF"}</span><span>Preview only</span></div><h3>何を相談しますか？</h3><textarea id="agent-intent">この場所に何を作ると港の景色が良くなる？</textarea><div class="action-row"><button class="primary" id="ask-agent">相談する</button><button class="secondary" id="agent-memory">記憶を見る</button></div></div>
      <div class="card"><h3>現在の権限</h3><p>近くの公開情報を読む · 自分の作品を読む · 施工Previewを作る。Commit、周囲の音声、Public Chat、Public Voice、自律移動は許可されていません。</p></div>
      <div class="action-row"><button class="danger" id="disconnect-agent">切断する</button></div>
    </div>` : `
    <div class="panel-grid">
      <div class="card"><h3>接続しても、権限は自動で増えません</h3><p>標準はPrivate・Read limited・Preview only・Voice offです。</p></div>
      <div class="card"><label for="pair-code"><strong>6桁のPair Code</strong></label><input id="pair-code" inputmode="numeric" maxlength="6" placeholder="123456"><div class="action-row"><button class="primary" id="pair-agent">接続</button><button class="secondary" id="local-agent">この端末のAgentを探す</button></div></div>
    </div>`;
  if (state.agentConnected) {
    overlayBody.querySelector("#ask-agent").addEventListener("click", () => showToast("Agentは現在の場所だけを読み、回答案を作りました"));
    overlayBody.querySelector("#agent-memory").addEventListener("click", () => showToast("標準はTask Memoryのみです"));
    overlayBody.querySelector("#disconnect-agent").addEventListener("click", () => { state.agentConnected = false; state.agentListening = false; updateIndicators(); renderAgent(); });
  } else {
    overlayBody.querySelector("#pair-agent").addEventListener("click", () => {
      const code = overlayBody.querySelector("#pair-code").value;
      if (!/^\d{6}$/.test(code)) return showToast("6桁のコードを入力してください");
      state.agentConnected = true;
      updateIndicators();
      renderAgent();
    });
    overlayBody.querySelector("#local-agent").addEventListener("click", () => showToast("ローカルUXプロトタイプでは検出を模擬しています"));
  }
}

function renderSocial() {
  setOverlayHeading("近くの人", "一緒に歩く・見せ合う");
  overlayBody.innerHTML = `<div class="panel-grid">${state.people.map((person) => `<div class="card"><h3>${person.name}</h3><p>${person.activity}</p><div class="action-row"><button class="primary" data-hello="${person.id}">こんにちは</button><button class="secondary" data-follow="${person.id}">ついていく</button><button class="secondary">作品を見る</button><button class="secondary">Partyへ招待</button></div></div>`).join("")}</div>`;
  for (const button of overlayBody.querySelectorAll("[data-hello]")) button.addEventListener("click", () => showToast("Waveと近距離チャットで挨拶しました"));
  for (const button of overlayBody.querySelectorAll("[data-follow]")) button.addEventListener("click", () => showToast("追従を開始しました。手動操作ですぐ解除できます"));
}

function renderVoice() {
  setOverlayHeading("Voice", "聞こえ方と話し方");
  overlayBody.innerHTML = `
    <div class="panel-grid">
      <div class="card"><h3>聞こえ方</h3><div class="action-row">${["spatial","lobby","hybrid","off"].map((mode) => `<button class="secondary" data-voice-mode="${mode}" aria-pressed="${state.voiceMode === mode}">${({ spatial:"空間", lobby:"ロビー", hybrid:"ハイブリッド", off:"音声なし" })[mode]}</button>`).join("")}</div><p>聞こえ方を変えても、マイクは自動でONになりません。</p></div>
      <div class="card"><h3>自分の声</h3><p>初期値はPush-to-talkです。このプロトタイプは実際のマイク権限を要求しません。</p><div class="action-row"><button class="primary" id="toggle-mic">${state.microphone ? "MICをOFFにする" : "MICを明示的にONにする"}</button><button class="secondary">デバイスを確認</button><button class="secondary">字幕</button></div></div>
      <div class="card"><h3>プライバシー</h3><p>録音OFF · Agent listening ${state.agentListening ? "ON" : "OFF"} · Public Agent Voice OFF</p></div>
    </div>`;
  for (const button of overlayBody.querySelectorAll("[data-voice-mode]")) button.addEventListener("click", () => { state.voiceMode = button.dataset.voiceMode; renderVoice(); });
  overlayBody.querySelector("#toggle-mic").addEventListener("click", () => { state.microphone = !state.microphone; if (!state.microphone) state.agentListening = false; updateIndicators(); renderVoice(); });
}

function renderMap() {
  setOverlayHeading("Map", "碧島");
  overlayBody.innerHTML = `<div class="card"><svg viewBox="0 0 600 300" role="img" aria-label="碧島の簡易地図" style="width:100%;border-radius:14px;background:#173c47"><path d="M65 165C92 75 206 35 322 57c103 19 207 97 194 169-14 75-143 56-221 44-91-14-257 3-230-105Z" fill="#579f72"/><circle cx="380" cy="104" r="10" fill="#fff"/><text x="397" y="109" fill="#fff">灯台</text><circle cx="252" cy="166" r="10" fill="#79e4b2"/><text x="269" y="171" fill="#fff">現在地</text><circle cx="185" cy="226" r="10" fill="#ffbf69"/><text x="202" y="231" fill="#fff">港</text></svg><div class="action-row"><button class="primary">Waypointを置く</button><button class="secondary">友だちの場所</button><button class="secondary">集合する</button></div></div>`;
}

function renderAvatar() {
  setOverlayHeading("Avatar", "自分の姿");
  overlayBody.innerHTML = `<div class="panel-grid"><div class="card"><h3>仮の姿ですぐ入れます</h3><p>アバター完成を入室条件にしません。後からCreator、VRMの安全なImport、Blenderによる高精細化を利用できます。</p></div><div class="card"><div class="action-row"><button class="primary" id="random-avatar">おまかせで変える</button><button class="secondary">顔</button><button class="secondary">髪</button><button class="secondary">服</button><button class="secondary">VRMを確認して読み込む</button></div></div></div>`;
  overlayBody.querySelector("#random-avatar").addEventListener("click", () => showToast("安全な仮アバターを更新しました"));
}

function renderInvite() {
  setOverlayHeading("Invite", "役割ごとに招待する");
  overlayBody.innerHTML = `<div class="panel-grid"><div class="card"><h3>見る人</h3><p>ブラウザですぐ参加。編集権限なし。</p><div class="action-row"><button class="primary">Viewerリンクを作る</button></div></div><div class="card"><h3>一緒につくる人</h3><p>Builder。期限、利用回数、Region、ホスト承認を設定できます。</p><div class="action-row"><button class="primary">Builderリンクを作る</button></div></div><div class="card"><h3>Blender Artist</h3><p>高精細Patchを作成できますが、Publish時に差分確認が必要です。</p><div class="action-row"><button class="secondary">Blender参加リンク</button></div></div></div>`;
}

function renderSettings() {
  setOverlayHeading("Settings", "表示と操作");
  overlayBody.innerHTML = `<div class="panel-grid"><div class="card"><h3>表示</h3><div class="action-row"><button class="secondary">軽量表示</button><button class="secondary">字幕</button><button class="secondary">高コントラスト</button><button class="secondary">動きを減らす</button></div></div><div class="card"><h3>上級者向け</h3><p>Cloudflare、MCP Endpoint、持ち込みLLM、Blender連携は普通の参加者には表示しません。</p><div class="action-row"><button class="secondary">詳細設定</button></div></div></div>`;
}

function renderPause() {
  setOverlayHeading("Pause", "碧島");
  overlayBody.innerHTML = `<div class="panel-grid"><button class="primary" id="resume-world">ワールドへ戻る</button><button class="secondary" data-open-inner="invite">招待する</button><button class="secondary" data-open-inner="avatar">姿を変える</button><button class="secondary" data-open-inner="voice">音声</button><button class="secondary" data-open-inner="settings">設定</button><button class="danger" id="return-lobby">ロビーへ戻る</button><p>マルチプレイ中のワールドはPauseしません。</p></div>`;
  overlayBody.querySelector("#resume-world").addEventListener("click", closeOverlay);
  overlayBody.querySelector("#return-lobby").addEventListener("click", () => { closeOverlay(); setMode("lobby"); state.microphone = false; state.agentListening = false; updateIndicators(); });
  for (const button of overlayBody.querySelectorAll("[data-open-inner]")) button.addEventListener("click", () => openOverlay(button.dataset.openInner));
}

function updateIndicators() {
  micIndicator.textContent = state.microphone ? "MIC ON" : "MIC OFF";
  micIndicator.setAttribute("aria-pressed", String(state.microphone));
  agentIndicator.textContent = state.agentConnected ? (state.agentListening ? "AGENT LISTENING" : "AGENT CONNECTED") : "AGENT OFF";
  agentIndicator.setAttribute("aria-pressed", String(state.agentListening));
}

document.querySelector("#primary-action").addEventListener("click", () => setMode("world"));
document.querySelector("#close-overlay").addEventListener("click", closeOverlay);
undoButton.addEventListener("click", undoLast);
micIndicator.addEventListener("click", () => openOverlay("voice"));
agentIndicator.addEventListener("click", () => openOverlay("agent"));
for (const button of document.querySelectorAll("[data-open]")) button.addEventListener("click", () => openOverlay(button.dataset.open));

chat.addEventListener("submit", (event) => {
  event.preventDefault();
  const input = document.querySelector("#chat-input");
  const message = input.value.trim();
  if (!message) return;
  const target = document.querySelector("#chat-target").value;
  if ((target === "Agent" || message.startsWith("@Agent")) && !state.agentConnected) {
    chat.hidden = true;
    openOverlay("agent");
    return;
  }
  showToast(`${target}へ送信しました`);
  input.value = "";
  chat.hidden = true;
  canvas.focus();
});

window.addEventListener("keydown", (event) => {
  const key = event.key.toLowerCase();
  const editable = event.target.matches?.("input, textarea, select");
  if (editable && key !== "escape") return;
  if (key === "enter" && state.mode === "lobby" && state.overlay === "none") { setMode("world"); return; }
  if (state.mode !== "world") return;
  if (["w", "a", "s", "d", "shift"].includes(key)) state.keys.add(key);
  if (key === "escape") { if (!chat.hidden) chat.hidden = true; else if (state.overlay !== "none") closeOverlay(); else openOverlay("pause"); event.preventDefault(); }
  if (state.overlay !== "none") return;
  if (key === "t") { chat.hidden = false; document.querySelector("#chat-input").focus(); event.preventDefault(); }
  if (key === "b" || key === "2") openOverlay("build");
  if ((event.altKey && key === "a") || key === "3") openOverlay("agent");
  if (key === "4") openOverlay("social");
  if (key === "5") openOverlay("voice");
  if (key === "6") openOverlay("map");
  if (key === "7") undoLast();
});
window.addEventListener("keyup", (event) => state.keys.delete(event.key.toLowerCase()));

canvas.addEventListener("pointerdown", (event) => { state.pointerDown = true; state.pointerX = event.clientX; canvas.setPointerCapture(event.pointerId); });
canvas.addEventListener("pointermove", (event) => {
  if (!state.pointerDown || state.mode !== "world") return;
  const movement = event.clientX - state.pointerX;
  state.pointerX = event.clientX;
  state.player.heading += movement * 0.006;
});
canvas.addEventListener("pointerup", (event) => {
  if (state.mode === "world" && Math.abs(event.clientX - state.pointerX) < 8) {
    const target = screenToWorld(event.clientX, event.clientY);
    state.target.x = clamp(target.x, -82, 82);
    state.target.z = clamp(target.z, -82, 82);
    updateLocation();
  }
  state.pointerDown = false;
});

resize();
updateIndicators();
updateLocation();
requestAnimationFrame(render);

window.OpenCraftPrototype = Object.freeze({
  getState: () => ({ mode: state.mode, overlay: state.overlay, hasPreview: Boolean(state.preview), historyLength: state.history.length, microphone: state.microphone, agentConnected: state.agentConnected, agentListening: state.agentListening }),
  setMode,
  openOverlay,
  closeOverlay,
});
