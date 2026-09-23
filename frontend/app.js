// ==========================================
// Config & State Management
// ==========================================
let config = {
  secondBrainUrl: "http://127.0.0.1:8000",
  antigravityUrl: "http://127.0.0.1:56523",
  access_token: "",
  theme: "cyber-noir",
  activeTab: "dashboard",
  visibleWidgets: ["widget-telemetry", "widget-capture", "widget-recent", "widget-antigravity"],
  workspacePath: ""
};

let brainData = {
  notes: {},
  graph: { nodes: [], links: [] }
};

let filteredNotes = [];
let connectionStatus = "OFFLINE"; // ONLINE | OFFLINE | FALLBACK

// Load settings from localStorage
function loadSettings() {
  const savedUrl = localStorage.getItem("sb_url");
  if (savedUrl) config.secondBrainUrl = savedUrl;
  
  if (config.secondBrainUrl.includes("localhost:8000")) {
    config.secondBrainUrl = config.secondBrainUrl.replace("localhost:8000", "127.0.0.1:8000");
    localStorage.setItem("sb_url", config.secondBrainUrl);
  }
  
  const savedAgUrl = localStorage.getItem("ag_url");
  if (savedAgUrl) config.antigravityUrl = savedAgUrl;
  
  const savedToken = localStorage.getItem("sb_token");
  if (savedToken) config.access_token = savedToken;
  
  const savedTheme = localStorage.getItem("sb_theme");
  if (savedTheme) {
    config.theme = savedTheme;
    document.body.className = `theme-${savedTheme}`;
  }
  
  const savedWidgets = localStorage.getItem("sb_widgets");
  if (savedWidgets) {
    try {
      config.visibleWidgets = JSON.parse(savedWidgets);
    } catch(e) {}
  }
  
  const savedWorkspace = localStorage.getItem("sb_workspace");
  if (savedWorkspace) config.workspacePath = savedWorkspace;
}

// Save settings
function saveSettings() {
  localStorage.setItem("sb_url", config.secondBrainUrl);
  localStorage.setItem("ag_url", config.antigravityUrl);
  localStorage.setItem("sb_token", config.access_token);
  localStorage.setItem("sb_theme", config.theme);
  localStorage.setItem("sb_widgets", JSON.stringify(config.visibleWidgets));
  localStorage.setItem("sb_workspace", config.workspacePath);
}

// ---------------------------------------------------------------------------
// DOM Initialization
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", async () => {
  loadSettings();
  initFormInputs();

  // Auto-discover Antigravity IDE port on startup
  try {
    const disc = await fetch("/api/antigravity/discover");
    const discData = await disc.json();
    if (discData.url && discData.url !== config.antigravityUrl) {
      config.antigravityUrl = discData.url;
      // Update the settings input to reflect the discovered URL
      const agInput = document.getElementById("cfg-ag-url");
      if (agInput) agInput.value = discData.url;
      console.log("[AG] Auto-discovered IDE at:", discData.url);
      // Persist the auto-discovered port so next checks use the correct address directly
      saveSettings();
    }
  } catch(e) {
    console.warn("[AG] Auto-discovery failed:", e.message);
  }

  await updateConnectionStatus();
  await loadDashboardData();
  
  // Load offline badge and active logs on startup
  updateOfflineBadge();
  fetchClientLogs();
  
  // Start periodically checking connection status
  setInterval(updateConnectionStatus, 15000);
  
  // Set up resize listener (clean fallback since D3 canvas was removed)
  window.addEventListener("resize", () => {
    // No action needed for split-pane layout which uses pure CSS grid
  });
});

function initFormInputs() {
  document.getElementById("cfg-url").value = config.secondBrainUrl;
  document.getElementById("cfg-ag-url").value = config.antigravityUrl;
  document.getElementById("cfg-token").value = config.access_token;
  document.getElementById("cfg-workspace").value = config.workspacePath || "";
  
  // Set checkboxes
  config.visibleWidgets.forEach(wid => {
    const chk = document.getElementById(`chk-${wid}`);
    if (chk) chk.checked = true;
    const el = document.getElementById(wid);
    if (el) el.classList.remove("hidden");
  });
  
  // Hide non-selected widgets
  const allWidgets = ["widget-telemetry", "widget-capture", "widget-recent", "widget-antigravity"];
  allWidgets.forEach(wid => {
    if (!config.visibleWidgets.includes(wid)) {
      const chk = document.getElementById(`chk-${wid}`);
      if (chk) chk.checked = false;
      const el = document.getElementById(wid);
      if (el) el.classList.add("hidden");
    }
  });
}

// ---------------------------------------------------------------------------
// Connection & APIs
// ---------------------------------------------------------------------------
async function updateConnectionStatus() {
  const pill = document.getElementById("conn-pill");
  const dot = document.getElementById("conn-dot");
  const text = document.getElementById("conn-text");
  
  try {
    const res = await fetch(`/api/secondbrain/status?target_url=${encodeURIComponent(config.secondBrainUrl)}`);
    const data = await res.json();
    
    if (data.status === "ONLINE") {
      connectionStatus = "ONLINE";
      pill.className = "connection-pill indicator-online";
      text.innerText = "ONLINE";
      document.getElementById("footer-status-label").innerText = "Local Connected";
      document.getElementById("footer-status-label").style.color = "var(--accent-green)";
      // Sync any offline queued notes when transitioning ONLINE
      syncOfflineQueue();
    } else {
      connectionStatus = "OFFLINE";
      pill.className = "connection-pill indicator-offline";
      text.innerText = "OFFLINE";
      document.getElementById("footer-status-label").innerText = "Disconnected";
      document.getElementById("footer-status-label").style.color = "var(--accent-red)";
    }
  } catch (err) {
    connectionStatus = "OFFLINE";
    pill.className = "connection-pill indicator-offline";
    text.innerText = "OFFLINE";
    document.getElementById("footer-status-label").innerText = "Disconnected";
    document.getElementById("footer-status-label").style.color = "var(--accent-red)";
  }

  // Also check Antigravity status
  await updateAntigravityStatus();
}

async function updateAntigravityStatus() {
  const pill = document.getElementById("ag-conn-pill");
  const dot = document.getElementById("ag-conn-dot");
  const text = document.getElementById("ag-conn-text");
  
  // Widget elements
  const widgetStatus = document.getElementById("ag-val-status");
  const widgetVersion = document.getElementById("ag-val-version");
  const widgetProject = document.getElementById("ag-val-project");
  const widgetCsrf = document.getElementById("ag-val-csrf");
  const widgetStatusDot = document.getElementById("ag-status-dot");
  
  try {
    const res = await fetch(`/api/antigravity/status?target_url=${encodeURIComponent(config.antigravityUrl)}`);
    const data = await res.json();
    
    if (data.status === "ONLINE") {
      pill.className = "connection-pill indicator-online";
      text.innerText = "AG: ONLINE";
      
      if (widgetStatus) {
        widgetStatus.innerText = "ONLINE";
        widgetStatus.className = "static-val text-online";
      }
      if (widgetStatusDot) {
        widgetStatusDot.style.backgroundColor = "var(--accent-green)";
        widgetStatusDot.style.boxShadow = "0 0 8px var(--accent-green-glow)";
      }
      
      const appConfig = data.config || {};
      if (widgetVersion) widgetVersion.innerText = appConfig.appVersion || "v1.0.0-dev";
      if (widgetProject) widgetProject.innerText = appConfig.projectId || "active_workspace";
      if (widgetCsrf) widgetCsrf.innerText = appConfig.csrfToken || "Local Secret Node";
    } else {
      setAntigravityOffline(pill, text, widgetStatus, widgetVersion, widgetProject, widgetCsrf, widgetStatusDot);
    }
  } catch (err) {
    setAntigravityOffline(pill, text, widgetStatus, widgetVersion, widgetProject, widgetCsrf, widgetStatusDot);
  }
}

function setAntigravityOffline(pill, text, widgetStatus, widgetVersion, widgetProject, widgetCsrf, widgetStatusDot) {
  pill.className = "connection-pill indicator-offline";
  text.innerText = "AG: OFFLINE";
  
  if (widgetStatus) {
    widgetStatus.innerText = "OFFLINE";
    widgetStatus.className = "static-val text-offline";
  }
  if (widgetStatusDot) {
    widgetStatusDot.style.backgroundColor = "var(--accent-red)";
    widgetStatusDot.style.boxShadow = "0 0 8px rgba(239, 68, 68, 0.5)";
  }
  if (widgetVersion) widgetVersion.innerText = "n/a";
  if (widgetProject) widgetProject.innerText = "ninguno";
  if (widgetCsrf) widgetCsrf.innerText = "n/a";
}

async function testConnection() {
  const urlInput = document.getElementById("cfg-url").value.trim();
  
  try {
    const res = await fetch(`/api/secondbrain/status?target_url=${encodeURIComponent(urlInput)}`);
    const data = await res.json();
    
    if (data.status === "ONLINE") {
      alert(`Conexión exitosa con Second Brain en: ${urlInput}`);
    } else {
      alert(`No se pudo conectar con Second Brain en: ${urlInput}. Asegúrate de que el servidor FastAPI esté encendido en ese puerto.`);
    }
  } catch (e) {
    alert(`Error de red al intentar verificar: ${e.message}`);
  }
  await updateConnectionStatus();
}

async function testAntigravityConnection() {
  const urlInput = document.getElementById("cfg-ag-url").value.trim();
  
  try {
    const res = await fetch(`/api/antigravity/status?target_url=${encodeURIComponent(urlInput)}`);
    const data = await res.json();
    
    if (data.status === "ONLINE") {
      alert(`Conexión exitosa con Antigravity IDE en: ${urlInput}`);
    } else {
      alert(`No se pudo conectar con el IDE en: ${urlInput}. Asegúrate de que el editor Antigravity esté activo.`);
    }
  } catch (e) {
    alert(`Error de red al intentar verificar: ${e.message}`);
  }
  await updateConnectionStatus();
}

async function saveConnectionSettings() {
  config.secondBrainUrl = document.getElementById("cfg-url").value.trim();
  config.antigravityUrl = document.getElementById("cfg-ag-url").value.trim();
  config.access_token = document.getElementById("cfg-token").value.trim();
  config.workspacePath = document.getElementById("cfg-workspace").value.trim();
  saveSettings();
  
  // Save workspace path to backend database as well
  try {
    const resConfig = await fetch("/api/dashboard/config", {
      headers: { "Authorization": `Bearer ${config.access_token}` }
    });
    const dbConfig = await resConfig.json();
    dbConfig.workspace_path = config.workspacePath;
    
    await fetch("/api/dashboard/config", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${config.access_token}`
      },
      body: JSON.stringify(dbConfig)
    });
  } catch(e) {
    console.warn("[Config] Failed to save workspace path to backend db:", e.message);
  }
  
  updateConnectionStatus();
  await loadDashboardData();
  alert("Configuración de conexión guardada.");
}

// ---------------------------------------------------------------------------
// Load & Render Dashboard Data
// ---------------------------------------------------------------------------
async function loadDashboardData() {
  const tbody = document.getElementById("recent-notes-tbody");
  tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-secondary); padding: 20px;">Cargando notas de Second Brain...</td></tr>`;

  try {
    const res = await fetch(`/api/secondbrain/proxy/index?target_url=${encodeURIComponent(config.secondBrainUrl)}`);
    const isFallback = res.headers.get("X-Offline-Fallback") === "True";
    const result = await res.json();
    
    const data = isFallback ? result.data : result;
    
    if (isFallback) {
      connectionStatus = "FALLBACK";
      const pill = document.getElementById("conn-pill");
      pill.className = "connection-pill indicator-fallback";
      document.getElementById("conn-text").innerText = `MODO CACHÉ (${result.cached_at})`;
      document.getElementById("footer-status-label").innerText = "Cache Offline Fallback";
      document.getElementById("footer-status-label").style.color = "var(--accent-amber)";
    }
    
    if (data && data.notes) {
      brainData.notes = data.notes;
      brainData.graph = data.graph;
      
      renderRecentNotesTable();
    }
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--accent-red); padding: 20px;">Error al conectar con el backend de proxy: ${err.message}.</td></tr>`;
    console.error(err);
  }
  
  // Async load of Agent & Workspace info
  await loadAgentSessions();
  await loadWorkspaceFiles();
}

// Removed old D3 tags calc and welcome screen tagbadges helper

// Search helper removed

// ---------------------------------------------------------------------------
// Recent Notes Table Rendering
// ---------------------------------------------------------------------------
function renderRecentNotesTable() {
  const tbody = document.getElementById("recent-notes-tbody");
  const notesList = Object.values(brainData.notes);
  
  if (notesList.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-secondary); padding: 20px;">No hay notas creadas en tu Second Brain.</td></tr>`;
    return;
  }
  
  // Sort by updated/created date descending
  notesList.sort((a, b) => {
    const dateA = a.updated || a.created || "";
    const dateB = b.updated || b.created || "";
    return dateB.localeCompare(dateA);
  });
  
  filteredNotes = notesList;
  displayNotesRows();
}

function displayNotesRows() {
  const tbody = document.getElementById("recent-notes-tbody");
  
  if (filteredNotes.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-secondary); padding: 20px;">No se encontraron notas que coincidan con la búsqueda.</td></tr>`;
    return;
  }
  
  // Display top 10 notes
  tbody.innerHTML = filteredNotes.slice(0, 10).map(note => {
    const statusClass = note.status === "draft" ? "draft" : "active";
    const dateStr = note.updated || note.created || "n/a";
    const tagBadges = note.tags.slice(0, 2).map(t => `<span style="font-size:0.65rem; color:var(--text-muted); margin-left: 5px;">#${t}</span>`).join("");
    
    return `
      <tr>
        <td><span class="category-pill cat-${note.category}">${note.category}</span></td>
        <td>
          <div style="font-weight: 600; color: white; cursor: pointer;" onclick="openNoteDetails('${note.category}', '${note.path}')">
            ${note.title} ${tagBadges}
          </div>
        </td>
        <td style="font-family: var(--font-mono); font-size: 0.75rem;">${dateStr}</td>
        <td>
          <div class="status-indicator">
            <span class="status-dot ${statusClass}"></span>
            <span>${note.status || "active"}</span>
          </div>
        </td>
        <td style="text-align: right;">
          <button class="btn btn-secondary" style="padding: 2px 8px; height: 24px; font-size: 0.7rem;" onclick="openNoteDetails('${note.category}', '${note.path}')">
            Ver Nota
          </button>
        </td>
      </tr>
    `;
  }).join("");
}

function filterRecentNotes() {
  const query = document.getElementById("notes-search-input").value.toLowerCase().trim();
  const notesList = Object.values(brainData.notes);
  
  if (query === "") {
    filteredNotes = notesList;
  } else {
    filteredNotes = notesList.filter(note => {
      return note.title.toLowerCase().includes(query) || 
             note.category.toLowerCase().includes(query) || 
             note.tags.some(tag => tag.toLowerCase().includes(query)) ||
             note.summary.toLowerCase().includes(query);
    });
  }
  displayNotesRows();
}

// ---------------------------------------------------------------------------
// Quick Capture Note Dispatcher
// ---------------------------------------------------------------------------
// Queue a note locally when offline
function enqueueOfflineNote(category, filename, payload) {
  let queue = [];
  try {
    queue = JSON.parse(localStorage.getItem("sb_offline_queue")) || [];
  } catch(e) {}
  
  queue.push({ category, filename, payload, timestamp: new Date().toISOString() });
  localStorage.setItem("sb_offline_queue", JSON.stringify(queue));
  updateOfflineBadge();
}

function updateOfflineBadge() {
  let queue = [];
  try {
    queue = JSON.parse(localStorage.getItem("sb_offline_queue")) || [];
  } catch(e) {}
  
  const badge = document.getElementById("offline-sync-badge");
  const count = document.getElementById("offline-sync-count");
  if (badge && count) {
    if (queue.length > 0) {
      count.innerText = queue.length;
      badge.classList.remove("hidden");
    } else {
      badge.classList.add("hidden");
    }
  }
}

// Sync all offline queued notes to the server
let isSyncingQueue = false;
async function syncOfflineQueue() {
  if (isSyncingQueue || connectionStatus !== "ONLINE") return;
  
  let queue = [];
  try {
    queue = JSON.parse(localStorage.getItem("sb_offline_queue")) || [];
  } catch(e) {}
  
  if (queue.length === 0) return;
  
  isSyncingQueue = true;
  console.log(`[Sync] Sincronizando ${queue.length} notas pendientes offline...`);
  
  let successCount = 0;
  let remainingQueue = [];
  
  for (let item of queue) {
    try {
      const res = await fetch(`/api/secondbrain/proxy/notes/${item.category}/${item.filename}?target_url=${encodeURIComponent(config.secondBrainUrl)}`, {
        method: "POST",
        headers: { 
          "Content-Type": "application/json",
          "Authorization": `Bearer ${config.access_token}`
        },
        body: JSON.stringify(item.payload)
      });
      if (res.ok) {
        successCount++;
      } else {
        remainingQueue.push(item);
      }
    } catch(err) {
      remainingQueue.push(item);
    }
  }
  
  localStorage.setItem("sb_offline_queue", JSON.stringify(remainingQueue));
  updateOfflineBadge();
  isSyncingQueue = false;
  
  if (successCount > 0) {
    console.log(`[Sync] Sincronizadas con éxito ${successCount} notas.`);
    await loadDashboardData(); // Refresh list
  }
}

async function submitQuickCapture() {
  const title = document.getElementById("cap-title").value.trim();
  const category = document.getElementById("cap-category").value;
  const rawTags = document.getElementById("cap-tags").value;
  const content = document.getElementById("cap-content").value;
  const isDraft = document.getElementById("cap-is-draft").checked;
  
  if (!title || !content) {
    alert("Por favor, introduce un título y contenido para la nota.");
    return;
  }
  
  const tags = rawTags.split(",").map(t => t.trim()).filter(t => t.length > 0);
  const payload = {
    title: title,
    content: content,
    tags: tags,
    status: isDraft ? "draft" : "active"
  };
  
  // Format filename cleanly
  const filename = title.toLowerCase().replace(/[^a-z0-9]/g, "-").replace(/-+/g, "-").replace(/^-|-$/g, "") + ".md";
  
  try {
    const res = await fetch(`/api/secondbrain/proxy/notes/${category}/${filename}?target_url=${encodeURIComponent(config.secondBrainUrl)}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${config.access_token}`
      },
      body: JSON.stringify(payload)
    });
    
    if (res.ok) {
      alert("Nota guardada exitosamente en tu Second Brain.");
      document.getElementById("cap-title").value = "";
      document.getElementById("cap-tags").value = "";
      document.getElementById("cap-content").value = "";
      document.getElementById("cap-is-draft").checked = true;
      await loadDashboardData();
    } else {
      // Server offline / proxy error: queue locally
      enqueueOfflineNote(category, filename, payload);
      alert("Servidor fuera de línea. La nota se ha encolado localmente y se sincronizará automáticamente al conectar.");
      document.getElementById("cap-title").value = "";
      document.getElementById("cap-tags").value = "";
      document.getElementById("cap-content").value = "";
      document.getElementById("cap-is-draft").checked = true;
    }
  } catch (e) {
    // Network error: queue locally
    enqueueOfflineNote(category, filename, payload);
    alert("Sin conexión. La nota se ha encolado localmente en tu dispositivo y se sincronizará automáticamente cuando reconectes.");
    document.getElementById("cap-title").value = "";
    document.getElementById("cap-tags").value = "";
    document.getElementById("cap-content").value = "";
    document.getElementById("cap-is-draft").checked = true;
  }
}

// ---------------------------------------------------------------------------
// SCoA Debate Courtroom (Server-Sent Events streaming)
// ---------------------------------------------------------------------------


// ---------------------------------------------------------------------------
// Open & Display Note Details Modal
// ---------------------------------------------------------------------------
let activeModalNotePath = "";

async function openNoteDetails(category, path) {
  const modal = document.getElementById("note-modal");
  const titleEl = document.getElementById("note-modal-title");
  const catEl = document.getElementById("note-modal-category");
  const updatedEl = document.getElementById("note-modal-updated");
  const tagsEl = document.getElementById("note-modal-tags");
  const contentEl = document.getElementById("note-modal-content");
  
  titleEl.innerText = "Cargando...";
  catEl.innerText = "";
  updatedEl.innerText = "";
  tagsEl.innerHTML = "";
  contentEl.innerText = "Cargando...";
  
  activeModalNotePath = path;
  modal.classList.add("active");
  
  try {
    const res = await fetch(`/api/secondbrain/proxy/notes/${category}/${path}?target_url=${encodeURIComponent(config.secondBrainUrl)}`);
    const note = await res.json();
    
    const data = note.is_cached ? note.data : note;
    
    titleEl.innerText = data.title || path;
    catEl.innerText = data.category || category;
    updatedEl.innerText = data.updated || data.created || "n/a";
    
    if (data.tags && data.tags.length > 0) {
      tagsEl.innerHTML = data.tags.map(t => `<span class="tag-badge">#${t}</span>`).join("");
    } else {
      tagsEl.innerHTML = `<span style="color:var(--text-muted); font-size:0.75rem;">Sin etiquetas</span>`;
    }
    
    contentEl.innerText = data.content || "Sin contenido.";
  } catch (err) {
    titleEl.innerText = "Error";
    contentEl.innerText = `No se pudieron cargar los detalles de la nota. El Second Brain local podría estar desconectado y esta nota no está en la caché: ${err.message}`;
  }
}

function closeNoteModal() {
  document.getElementById("note-modal").classList.remove("active");
}

function openInObsidianProtocol() {
  if (!activeModalNotePath) return;
  // Obsidian URI protocol links: obsidian://open?vault=vault&file=category/filename
  const relativePath = activeModalNotePath; // path includes category like 'ideas/note.md'
  const obsUrl = `obsidian://open?vault=vault&file=${encodeURIComponent(relativePath)}`;
  window.open(obsUrl, "_blank");
}

// ---------------------------------------------------------------------------
// Git Sync Remote Command
// ---------------------------------------------------------------------------
async function syncSecondBrain() {
  const btn = document.getElementById("sync-btn");
  btn.disabled = true;
  btn.querySelector("span").innerText = "Sincronizando...";
  
  try {
    const res = await fetch(`/api/secondbrain/proxy/git/sync?target_url=${encodeURIComponent(config.secondBrainUrl)}`, {
      method: "POST"
    });
    const data = await res.json();
    
    if (res.ok) {
      alert(`Sincronización Git completada con éxito: ${data.message || "Cambios subidos a GitHub."}`);
      document.getElementById("last-sync-time").innerText = new Date().toLocaleTimeString();
    } else {
      alert(`Fallo en la sincronización: ${data.detail || "Error en el comando git."}`);
    }
  } catch(e) {
    alert(`Error de red al sincronizar con el proxy: ${e.message}`);
  }
  
  btn.disabled = false;
  btn.querySelector("span").innerText = "Sincronizar Git";
}

// ---------------------------------------------------------------------------
// Navigation / Tab Switching
// ---------------------------------------------------------------------------
function switchTab(tabId) {
  // Hide all panels
  document.querySelectorAll('.tab-panel').forEach(panel => {
    panel.classList.remove('active');
  });
  
  // Deactivate sidebar nav items
  document.querySelectorAll('.nav-item').forEach(item => {
    item.classList.remove('active');
  });

  // Show active panel
  document.getElementById(`panel-${tabId}`).classList.add('active');
  
  const navItem = document.getElementById(`nav-${tabId}`);
  if (navItem) navItem.classList.add('active');

  // Toggle hide-header class on body if tab is antigravity-ide
  document.body.classList.toggle('hide-header', tabId === 'antigravity-ide');

  // Update header title
  const titles = {
    'dashboard': 'Panel General de Telemetría',
    'artifacts-view': 'Inspector de Artefactos y Código',
    'antigravity-ide': 'Editor Antigravity (IDE Remoto)',
    'widgets-config': 'Personalización de Consola HUD'
  };
  document.getElementById('current-page-title').innerText = titles[tabId] || 'Centro de Control';
  
  config.activeTab = tabId;
  
  if (tabId === 'artifacts-view') {
    loadAgentSessions();
    loadWorkspaceFiles();
  }
}

function updateMobileNav(tabId) {
  document.querySelectorAll('.mob-nav-btn').forEach(btn => {
    btn.classList.remove('active');
  });
  const activeBtn = document.getElementById(`mob-nav-${tabId}`);
  if (activeBtn) activeBtn.classList.add('active');
}

function toggleSidebar() {
  const sidebar = document.getElementById("app-sidebar");
  sidebar.classList.toggle("collapsed");
}

function toggleTheme() {
  config.theme = config.theme === "cyber-noir" ? "minimal-dark" : "cyber-noir";
  document.body.className = `theme-${config.theme}`;
  saveSettings();
}

function toggleWidgetVisibility(widgetId) {
  const chk = document.getElementById(`chk-${widgetId}`);
  const el = document.getElementById(widgetId);
  
  if (chk.checked) {
    if (!config.visibleWidgets.includes(widgetId)) config.visibleWidgets.push(widgetId);
    if (el) el.classList.remove("hidden");
  } else {
    config.visibleWidgets = config.visibleWidgets.filter(w => w !== widgetId);
    if (el) el.classList.add("hidden");
  }
  saveSettings();
}

// ==========================================================================
// Artifacts & Workspace Files Browser Logic
// ==========================================================================
let sessionsData = [];
let selectedSessionId = "";
let workspaceFiles = [];
let activeFile = null;
let viewerMode = "preview"; // preview | raw

async function calculateTelemetry() {
  const totalNotes = Object.keys(brainData.notes).length;
  const statTotal = document.getElementById("stat-total");
  if (statTotal) statTotal.innerText = totalNotes;
  
  const statSessions = document.getElementById("stat-sessions");
  if (statSessions) statSessions.innerText = sessionsData.length;
  
  const statWorkspaceFiles = document.getElementById("stat-workspace-files");
  if (statWorkspaceFiles) statWorkspaceFiles.innerText = workspaceFiles.length;
  
  // Active session files count
  const activeSession = sessionsData.find(s => s.id === selectedSessionId) || sessionsData[0];
  const activeCount = activeSession ? (activeSession.files ? activeSession.files.length : 0) : 0;
  const statArtifacts = document.getElementById("stat-artifacts");
  if (statArtifacts) statArtifacts.innerText = activeCount;
  
  const sessionLbl = document.getElementById("active-session-lbl");
  if (sessionLbl) {
    sessionLbl.innerText = activeSession ? `Session: ${activeSession.id.substring(0, 8)}...` : "Session: n/a";
  }
  
  // Render quick list in Dashboard
  const quickList = document.getElementById("recent-artifacts-list");
  if (quickList) {
    if (!activeSession || !activeSession.files || activeSession.files.length === 0) {
      quickList.innerHTML = `<div style="color:var(--text-muted); font-size:0.75rem; padding: 4px 0;">No hay artefactos en la sesión activa</div>`;
      return;
    }
    
    // Sort files by date descending
    const sorted = [...activeSession.files].sort((a, b) => b.updated_at.localeCompare(a.updated_at));
    
    quickList.innerHTML = sorted.slice(0, 4).map(file => {
      let icon = "📄";
      if (file.name.includes("plan")) icon = "📝";
      else if (file.name.includes("task")) icon = "✅";
      else if (file.name.includes("walkthrough")) icon = "🚀";
      else if (file.name.endsWith(".py")) icon = "🐍";
      
      return `
        <div class="artifact-quick-item" onclick="openArtifactFromDashboard('${activeSession.id}', '${file.path}')">
          <span class="artifact-quick-name">${icon} ${file.name}</span>
          <span class="artifact-quick-date">${file.updated_at.split(" ")[1] || ""}</span>
        </div>
      `;
    }).join("");
  }
}

async function loadAgentSessions() {
  try {
    const res = await fetch("/api/antigravity/sessions", {
      headers: { "Authorization": `Bearer ${config.access_token}` }
    });
    sessionsData = await res.json();
    
    const select = document.getElementById("artifacts-session-select");
    if (select) {
      select.innerHTML = sessionsData.map(s => {
        const dateStr = s.updated_at ? s.updated_at.substring(5, 16) : "n/a"; // MM-DD HH:MM
        const isCurrent = s.id === "55d599ae-7d7e-4666-b308-76e14a9a209d" ? " (Actual)" : "";
        return `<option value="${s.id}">${s.id.substring(0, 8)}... (${dateStr})${isCurrent}</option>`;
      }).join("");
      
      // Default to current session or the most recent one
      const currentExists = sessionsData.some(s => s.id === "55d599ae-7d7e-4666-b308-76e14a9a209d");
      const defaultSessionId = currentExists ? "55d599ae-7d7e-4666-b308-76e14a9a209d" : (sessionsData[0] ? sessionsData[0].id : "");
      
      if (defaultSessionId) {
        select.value = defaultSessionId;
        selectedSessionId = defaultSessionId;
        renderSessionArtifacts(defaultSessionId);
      }
    }
    
    await calculateTelemetry();
  } catch (e) {
    console.error("[Sessions] Error al cargar sesiones del agente:", e);
    const container = document.getElementById("session-artifacts-list");
    if (container) {
      container.innerHTML = `<div class="empty-state" style="color:var(--accent-red)">Error al conectar con la API de sesiones</div>`;
    }
  }
}

async function onSessionChange() {
  const select = document.getElementById("artifacts-session-select");
  if (select) {
    selectedSessionId = select.value;
    renderSessionArtifacts(selectedSessionId);
    await calculateTelemetry();
  }
}

function renderSessionArtifacts(sessionId) {
  const container = document.getElementById("session-artifacts-list");
  if (!container) return;
  
  const session = sessionsData.find(s => s.id === sessionId);
  if (!session || !session.files || session.files.length === 0) {
    container.innerHTML = `<div class="empty-state">No hay artefactos en esta sesión</div>`;
    return;
  }
  
  // Sort files: implementation_plan, task, walkthrough first, then alphabetical
  const filesCopy = [...session.files];
  filesCopy.sort((a, b) => {
    const getPriority = (name) => {
      if (name.includes("implementation_plan")) return 1;
      if (name.includes("task")) return 2;
      if (name.includes("walkthrough")) return 3;
      return 100;
    };
    const pA = getPriority(a.name);
    const pB = getPriority(b.name);
    if (pA !== pB) return pA - pB;
    return a.name.localeCompare(b.name);
  });
  
  container.innerHTML = filesCopy.map(file => {
    let icon = "📄";
    if (file.name.includes("implementation_plan")) icon = "📝";
    else if (file.name.includes("task")) icon = "✅";
    else if (file.name.includes("walkthrough")) icon = "🚀";
    else if (file.name.endsWith(".py")) icon = "🐍";
    else if (file.name.endsWith(".log")) icon = "📋";
    
    const isActive = activeFile && activeFile.source === 'artifact' && activeFile.sessionId === sessionId && activeFile.path === file.path ? 'active' : '';
    const sizeKb = (file.size / 1024).toFixed(1) + " KB";
    
    return `
      <div class="file-item ${isActive}" onclick="viewArtifactFile('${sessionId}', '${file.path}')">
        <span class="file-icon">${icon}</span>
        <span class="file-name-txt" title="${file.name}">${file.name}</span>
        <span class="file-size-txt">${sizeKb}</span>
      </div>
    `;
  }).join("");
}

async function loadWorkspaceFiles() {
  const container = document.getElementById("workspace-files-list");
  if (container) {
    container.innerHTML = `<div class="empty-state">Buscando archivos...</div>`;
  }
  
  try {
    const res = await fetch(`/api/workspace/files?workspace=${encodeURIComponent(config.workspacePath)}`, {
      headers: { "Authorization": `Bearer ${config.access_token}` }
    });
    const data = await res.json();
    workspaceFiles = data.files || [];
    renderWorkspaceFiles();
    await calculateTelemetry();
  } catch (e) {
    console.error("[Workspace] Error al cargar archivos:", e);
    if (container) {
      container.innerHTML = `<div class="empty-state" style="color:var(--accent-red)">Error al leer archivos del proyecto</div>`;
    }
  }
}

function renderWorkspaceFiles() {
  const container = document.getElementById("workspace-files-list");
  if (!container) return;
  
  if (workspaceFiles.length === 0) {
    container.innerHTML = `<div class="empty-state">No se encontraron archivos en la ruta del proyecto</div>`;
    return;
  }
  
  const sorted = [...workspaceFiles].sort((a, b) => a.path.localeCompare(b.path));
  
  container.innerHTML = sorted.map(file => {
    let icon = "📄";
    if (file.name.endsWith(".py")) icon = "🐍";
    else if (file.name.endsWith(".js")) icon = "🟨";
    else if (file.name.endsWith(".html")) icon = "🌐";
    else if (file.name.endsWith(".css")) icon = "🎨";
    else if (file.name.endsWith(".json")) icon = "⚙️";
    else if (file.name.endsWith(".md")) icon = "📝";
    else if (file.name.endsWith(".bat") || file.name.endsWith(".ps1")) icon = "⚡";
    
    const isActive = activeFile && activeFile.source === 'workspace' && activeFile.path === file.path ? 'active' : '';
    const sizeKb = (file.size / 1024).toFixed(1) + " KB";
    
    return `
      <div class="file-item ${isActive}" onclick="viewWorkspaceFile('${file.path}')" data-path="${file.path.toLowerCase()}">
        <span class="file-icon">${icon}</span>
        <span class="file-name-txt" title="${file.path}">${file.path}</span>
        <span class="file-size-txt">${sizeKb}</span>
      </div>
    `;
  }).join("");
}

function filterWorkspaceFiles() {
  const query = document.getElementById("workspace-search").value.toLowerCase().trim();
  const items = document.querySelectorAll("#workspace-files-list .file-item");
  
  items.forEach(item => {
    const path = item.getAttribute("data-path");
    if (path.includes(query)) {
      item.classList.remove("hidden");
    } else {
      item.classList.add("hidden");
    }
  });
}

async function viewArtifactFile(sessionId, filePath) {
  document.getElementById("viewer-welcome-screen").classList.add("hidden");
  document.getElementById("viewer-loading-screen").classList.remove("hidden");
  document.getElementById("code-viewer-container").classList.add("hidden");
  document.getElementById("markdown-previewer-container").classList.add("hidden");
  document.getElementById("inspector-file-header").style.display = "none";
  
  try {
    const res = await fetch(`/api/antigravity/artifact?session_id=${sessionId}&path=${encodeURIComponent(filePath)}`, {
      headers: { "Authorization": `Bearer ${config.access_token}` }
    });
    const file = await res.json();
    
    activeFile = {
      source: 'artifact',
      sessionId,
      path: filePath,
      name: file.name,
      content: file.content,
      size: file.size,
      updated_at: file.updated_at
    };
    
    displayFileInInspector();
  } catch (e) {
    console.error("[Artifact] Error al ver archivo:", e);
    alert("No se pudo cargar el archivo");
    document.getElementById("viewer-welcome-screen").classList.add("hidden");
    document.getElementById("viewer-loading-screen").classList.add("hidden");
  }
}

async function viewWorkspaceFile(filePath) {
  document.getElementById("viewer-welcome-screen").classList.add("hidden");
  document.getElementById("viewer-loading-screen").classList.remove("hidden");
  document.getElementById("code-viewer-container").classList.add("hidden");
  document.getElementById("markdown-previewer-container").classList.add("hidden");
  document.getElementById("inspector-file-header").style.display = "none";
  
  try {
    const res = await fetch(`/api/workspace/file/content?path=${encodeURIComponent(filePath)}&workspace=${encodeURIComponent(config.workspacePath)}`, {
      headers: { "Authorization": `Bearer ${config.access_token}` }
    });
    
    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.detail || "Error al leer archivo");
    }
    
    const file = await res.json();
    
    activeFile = {
      source: 'workspace',
      path: filePath,
      name: file.name,
      content: file.content,
      size: file.size,
      updated_at: file.updated_at
    };
    
    displayFileInInspector();
  } catch (e) {
    console.error("[Workspace] Error al ver archivo:", e);
    alert(`No se pudo cargar el archivo: ${e.message}`);
    document.getElementById("viewer-welcome-screen").classList.add("hidden");
    document.getElementById("viewer-loading-screen").classList.add("hidden");
  }
}

function displayFileInInspector() {
  if (!activeFile) return;
  
  if (activeFile.source === 'artifact') {
    renderSessionArtifacts(activeFile.sessionId);
    document.querySelectorAll("#workspace-files-list .file-item").forEach(item => item.classList.remove("active"));
  } else {
    renderWorkspaceFiles();
  }
  
  document.getElementById("inspector-file-name").innerText = activeFile.name;
  document.getElementById("inspector-file-path").innerText = `${activeFile.source === 'artifact' ? 'brain/' + activeFile.sessionId.substring(0,8) + '.../' : ''}${activeFile.path}`;
  document.getElementById("inspector-file-size").innerText = (activeFile.size / 1024).toFixed(1) + " KB";
  document.getElementById("inspector-file-date").innerText = activeFile.updated_at || "n/a";
  document.getElementById("inspector-file-header").style.display = "flex";
  
  const mdToggleGroup = document.getElementById("markdown-toggle-group");
  if (activeFile.name.endsWith(".md")) {
    mdToggleGroup.style.display = "flex";
  } else {
    mdToggleGroup.style.display = "none";
    viewerMode = "raw";
  }
  
  document.getElementById("btn-mode-preview").className = `btn btn-secondary ${viewerMode === 'preview' ? 'active' : ''}`;
  document.getElementById("btn-mode-raw").className = `btn btn-secondary ${viewerMode === 'raw' ? 'active' : ''}`;
  
  document.getElementById("viewer-loading-screen").classList.add("hidden");
  renderFileContent();
}

function renderFileContent() {
  const codeContainer = document.getElementById("code-viewer-container");
  const mdContainer = document.getElementById("markdown-previewer-container");
  
  if (activeFile.name.endsWith(".md") && viewerMode === "preview") {
    codeContainer.classList.add("hidden");
    mdContainer.classList.remove("hidden");
    mdContainer.innerHTML = parseMarkdown(activeFile.content);
  } else {
    mdContainer.classList.add("hidden");
    codeContainer.classList.remove("hidden");
    
    const codeEl = document.getElementById("code-viewer-content").querySelector("code");
    codeEl.innerText = activeFile.content;
    
    const lines = activeFile.content.split("\n");
    const lineNumbersEl = document.getElementById("code-viewer-line-numbers");
    lineNumbersEl.innerHTML = lines.map((_, i) => i + 1).join("\n");
  }
}

function setViewerMode(mode) {
  viewerMode = mode;
  document.getElementById("btn-mode-preview").className = `btn btn-secondary ${mode === 'preview' ? 'active' : ''}`;
  document.getElementById("btn-mode-raw").className = `btn btn-secondary ${mode === 'raw' ? 'active' : ''}`;
  renderFileContent();
}

function copyInspectorContent() {
  if (!activeFile) return;
  navigator.clipboard.writeText(activeFile.content)
    .then(() => alert("¡Contenido copiado al portapapeles!"))
    .catch(err => alert("Error al copiar al portapapeles: " + err));
}

function downloadInspectorFile() {
  if (!activeFile) return;
  const blob = new Blob([activeFile.content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = activeFile.name;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function openArtifactFromDashboard(sessionId, filePath) {
  switchTab('artifacts-view');
  setTimeout(async () => {
    const select = document.getElementById("artifacts-session-select");
    if (select) {
      select.value = sessionId;
      selectedSessionId = sessionId;
      await onSessionChange();
      await viewArtifactFile(sessionId, filePath);
    }
  }, 100);
}

function openFileFromMarkdownLink(absolutePath) {
  let wsPath = config.workspacePath || "";
  let relPath = absolutePath;
  const cleanAbs = absolutePath.replace(/\\/g, "/").toLowerCase();
  const cleanWs = wsPath.replace(/\\/g, "/").toLowerCase();
  
  if (cleanAbs.startsWith(cleanWs)) {
    relPath = absolutePath.substring(cleanWs.length);
    if (relPath.startsWith("/") || relPath.startsWith("\\")) {
      relPath = relPath.substring(1);
    }
  }
  
  viewWorkspaceFile(relPath);
}

function parseMarkdown(md) {
  if (!md) return "";
  
  let html = md
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
    
  html = html.replace(/^- \`\[ \]\` (.*)$/gm, '<div class="markdown-task-item"><span class="markdown-task-checkbox unchecked"></span><span class="markdown-task-text">$1</span></div>');
  html = html.replace(/^- \`\[x\]\` (.*)$/gm, '<div class="markdown-task-item"><span class="markdown-task-checkbox checked">✓</span><span class="markdown-task-text completed">$1</span></div>');
  html = html.replace(/^- \`\[\/\]\` (.*)$/gm, '<div class="markdown-task-item"><span class="markdown-task-checkbox in-progress">⏳</span><span class="markdown-task-text in-progress">$1</span></div>');
  
  html = html.replace(/^- \[\s\] (.*)$/gm, '<div class="markdown-task-item"><span class="markdown-task-checkbox unchecked"></span><span class="markdown-task-text">$1</span></div>');
  html = html.replace(/^- \[x\] (.*)$/gm, '<div class="markdown-task-item"><span class="markdown-task-checkbox checked">✓</span><span class="markdown-task-text completed">$1</span></div>');
  
  html = html.replace(/^#### (.*)$/gm, "<h4>$1</h4>");
  html = html.replace(/^### (.*)$/gm, "<h3>$1</h3>");
  html = html.replace(/^## (.*)$/gm, "<h2>$1</h2>");
  html = html.replace(/^# (.*)$/gm, "<h1>$1</h1>");
  
  html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*(.*?)\*/g, "<em>$1</em>");
  
  html = html.replace(/\[(.*?)\]\((file:\/\/\/.*?)\)/gi, (match, text, url) => {
    const prefix = "file:///";
    let cleanPath = url;
    if (url.startsWith(prefix)) {
      cleanPath = url.substring(prefix.length);
    }
    return `<a href="#" onclick="openFileFromMarkdownLink('${cleanPath.replace(/\\/g, "/")}')" style="color:var(--accent-purple); text-decoration:underline;">${text}</a>`;
  });
  
  html = html.replace(/^\* (.*)$/gm, "<li>$1</li>");
  html = html.replace(/^- (?!<div)(.*)$/gm, "<li>$1</li>");
  
  html = html.replace(/```([\s\S]*?)```/g, "<pre><code>$1</code></pre>");
  html = html.replace(/`(.*?)`/g, "<code>$1</code>");
  
  const lines = html.split("\n");
  html = lines.map(line => {
    const trimmed = line.trim();
    if (!trimmed) return "";
    if (trimmed.startsWith("<h") || trimmed.startsWith("<div") || trimmed.startsWith("<li") || trimmed.startsWith("<pre") || trimmed.startsWith("</pre>") || trimmed.startsWith("<code>")) {
      return line;
    }
    return `<p>${line}</p>`;
  }).join("\n");
  
  return html;
}

// Security: Change Password
// ---------------------------------------------------------------------------
async function changeAdminPassword() {
  const oldPwd = document.getElementById("pwd-old").value;
  const newPwd = document.getElementById("pwd-new").value;
  
  if (!oldPwd || !newPwd) {
    alert("Por favor, introduce la contraseña actual y la nueva contraseña.");
    return;
  }
  
  try {
    const res = await fetch("/api/auth/change-password", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${config.access_token}`
      },
      body: JSON.stringify({ old_password: oldPwd, new_password: newPwd })
    });
    const data = await res.json();
    if (res.ok) {
      alert("Contraseña actualizada exitosamente.");
      document.getElementById("pwd-old").value = "";
      document.getElementById("pwd-new").value = "";
    } else {
      alert(`Error al cambiar la contraseña: ${data.detail || "Error desconocido"}`);
    }
  } catch(e) {
    alert(`Error de red: ${e.message}`);
  }
}

// ---------------------------------------------------------------------------
// Debugging: Log Capture
// ---------------------------------------------------------------------------
async function toggleLogCapture() {
  const chk = document.getElementById("chk-log-capture");
  const isChecked = chk.checked;
  const wrapper = document.getElementById("log-console-wrapper");
  
  try {
    // Fetch current config
    const resConfig = await fetch("/api/dashboard/config", {
      headers: { "Authorization": `Bearer ${config.access_token}` }
    });
    const dbConfig = await resConfig.json();
    
    // Update setting
    dbConfig.log_capture_enabled = isChecked;
    
    // Save config
    await fetch("/api/dashboard/config", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${config.access_token}`
      },
      body: JSON.stringify(dbConfig)
    });
    
    if (isChecked) {
      wrapper.classList.remove("hidden");
      fetchClientLogs();
    } else {
      wrapper.classList.add("hidden");
    }
  } catch(e) {
    console.error("[Logs] Error al guardar configuración de logs:", e);
  }
}

async function fetchClientLogs() {
  const consoleEl = document.getElementById("client-logs-console");
  if (!consoleEl) return;
  
  try {
    const res = await fetch("/api/debug/logs", {
      headers: { "Authorization": `Bearer ${config.access_token}` }
    });
    const data = await res.json();
    
    // Update checkbox state on load
    const chk = document.getElementById("chk-log-capture");
    if (chk) chk.checked = data.enabled;
    const wrapper = document.getElementById("log-console-wrapper");
    if (wrapper) {
      if (data.enabled) wrapper.classList.remove("hidden");
      else wrapper.classList.add("hidden");
    }
    
    if (!data.enabled) {
      consoleEl.innerText = "Logs inactivos. Activa la casilla de arriba para iniciar la captura de logs.";
      return;
    }
    
    if (data.logs.length === 0) {
      consoleEl.innerText = "No hay logs registrados en esta sesión.";
      return;
    }
    
    consoleEl.innerText = data.logs.map(log => {
      const errorText = log.error ? `\nStack:\n${log.error}` : "";
      return `[${log.timestamp}] ${log.message}${errorText}`;
    }).join("\n\n");
    
    consoleEl.scrollTop = consoleEl.scrollHeight; // Auto-scroll
  } catch(e) {
    consoleEl.innerText = `Error al consultar logs: ${e.message}`;
  }
}

async function clearClientLogs() {
  const consoleEl = document.getElementById("client-logs-console");
  try {
    const res = await fetch("/api/debug/logs", {
      method: "DELETE",
      headers: { "Authorization": `Bearer ${config.access_token}` }
    });
    if (res.ok) {
      if (consoleEl) consoleEl.innerText = "Logs de cliente limpiados.";
    }
  } catch(e) {
    if (consoleEl) consoleEl.innerText = `Error al limpiar logs: ${e.message}`;
  }
}
