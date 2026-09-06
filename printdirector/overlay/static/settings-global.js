const APPEARANCE_DEFAULTS = {
  theme: 'dark', background_color: '#0b0e14', text_color: '#f5f7fa', accent_color: '#38bdf8',
  panel_opacity: 0.92, font_family: 'system-ui', font_scale: 1,
  show_filename: true, show_state: true, show_eta: true, show_temps: true, show_layers: true,
  printer_overrides: {}
};
const APPEARANCE_PRESETS = {
  dark: { theme: 'dark', background_color: '#0b0e14', text_color: '#f5f7fa', accent_color: '#38bdf8', panel_opacity: 0.92, font_scale: 1 },
  light: { theme: 'light', background_color: '#f8fafc', text_color: '#0f172a', accent_color: '#0ea5e9', panel_opacity: 0.86, font_scale: 1 },
  mint: { theme: 'dark', background_color: '#071b16', text_color: '#e6fffb', accent_color: '#34d399', panel_opacity: 0.9, font_scale: 1.08 },
  sunset: { theme: 'dark', background_color: '#1f0c12', text_color: '#fff1f2', accent_color: '#f97316', panel_opacity: 0.88, font_scale: 1.08 }
};

const $ = (id) => document.getElementById(id);
const deepClone = (value) => JSON.parse(JSON.stringify(value));
let overlaySettings = { ...APPEARANCE_DEFAULTS, printer_overrides: {} };
let runtimeConfig = { printers: [], obs: {}, overlay: {}, auth: {} };
let printerStatuses = {};

function getToken() {
  const saved = localStorage.getItem('printdirector-token');
  if (saved && saved.trim()) return saved.trim();
  const fromQuery = new URLSearchParams(window.location.search).get('token');
  return fromQuery ? fromQuery.trim() : null;
}
function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
function stamp() { return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); }
function setPageStatus(message, ok = true) {
  const node = $('settings-status');
  if (!node) return;
  node.textContent = `${message} • ${stamp()}`;
  node.dataset.state = ok ? 'ok' : 'error';
}

function activateSettingsSection(section) {
  document.querySelectorAll('.settings-tab').forEach((tab) => {
    const active = tab.dataset.section === section;
    tab.classList.toggle('active', active);
    tab.setAttribute('aria-selected', String(active));
  });
  document.querySelectorAll('[data-settings-section]').forEach((panel) => {
    panel.hidden = panel.dataset.settingsSection !== section;
  });
  if (section === 'printers' && window.renderPrintDirectorPrinterEditor) window.renderPrintDirectorPrinterEditor();
}

function appearanceFromControls() {
  return {
    ...APPEARANCE_DEFAULTS,
    theme: $('appearance-theme').value || 'dark',
    background_color: $('appearance-background').value,
    text_color: $('appearance-text').value,
    accent_color: $('appearance-accent').value,
    panel_opacity: Number($('appearance-opacity').value),
    font_family: $('appearance-font').value || 'system-ui',
    font_scale: Number($('appearance-scale').value),
    show_filename: $('appearance-show-filename').checked,
    show_state: $('appearance-show-state').checked,
    show_eta: $('appearance-show-eta').checked,
    show_temps: $('appearance-show-temps').checked,
    show_layers: $('appearance-show-layers').checked,
    printer_overrides: overlaySettings.printer_overrides || {}
  };
}
function populateAppearance(settings) {
  overlaySettings = { ...APPEARANCE_DEFAULTS, ...settings, printer_overrides: settings.printer_overrides || {} };
  $('appearance-theme').value = overlaySettings.theme;
  $('appearance-background').value = overlaySettings.background_color;
  $('appearance-text').value = overlaySettings.text_color;
  $('appearance-accent').value = overlaySettings.accent_color;
  $('appearance-opacity').value = String(overlaySettings.panel_opacity);
  $('appearance-font').value = overlaySettings.font_family;
  $('appearance-scale').value = String(overlaySettings.font_scale);
  $('appearance-show-filename').checked = overlaySettings.show_filename;
  $('appearance-show-state').checked = overlaySettings.show_state;
  $('appearance-show-eta').checked = overlaySettings.show_eta;
  $('appearance-show-temps').checked = overlaySettings.show_temps;
  $('appearance-show-layers').checked = overlaySettings.show_layers;
  renderGlobalPreview();
  if (window.renderPrintDirectorPrinterPreview) window.renderPrintDirectorPrinterPreview();
}
function applyCardPreview(card, settings, name = 'Printer preview') {
  if (!card) return;
  const theme = settings.theme || 'dark';
  const opacity = Number(settings.panel_opacity ?? APPEARANCE_DEFAULTS.panel_opacity);
  card.style.setProperty('--preview-accent', settings.accent_color || APPEARANCE_DEFAULTS.accent_color);
  card.style.background = theme === 'light' ? `rgba(255,255,255,${opacity})` : `rgba(13,18,28,${opacity})`;
  card.style.color = settings.text_color || APPEARANCE_DEFAULTS.text_color;
  card.style.fontFamily = settings.font_family || 'system-ui';
  card.style.fontSize = `${Number(settings.font_scale || 1).toFixed(2)}rem`;
  card.style.borderColor = settings.accent_color || APPEARANCE_DEFAULTS.accent_color;
  const nameNode = card.querySelector('[data-preview-name]');
  if (nameNode) nameNode.textContent = settings.label_override || name;
  const visibility = [
    ['[data-preview-state]', settings.show_state], ['[data-preview-file]', settings.show_filename],
    ['[data-preview-eta]', settings.show_eta], ['[data-preview-temps]', settings.show_temps],
    ['[data-preview-layers]', settings.show_layers]
  ];
  visibility.forEach(([selector, visible]) => { const node = card.querySelector(selector); if (node) node.hidden = !visible; });
  const fill = card.querySelector('.preview-bar i');
  if (fill) fill.style.background = settings.accent_color || APPEARANCE_DEFAULTS.accent_color;
}
function renderGlobalPreview() { applyCardPreview($('global-preview-card'), appearanceFromControls(), 'Jötunn'); }

async function saveAppearance() {
  const payload = appearanceFromControls();
  setPageStatus('Saving appearance…');
  const response = await fetch('/api/settings', {
    method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify(payload)
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) { setPageStatus(data.detail || 'Appearance save failed.', false); return false; }
  populateAppearance(data);
  setPageStatus('Appearance saved.');
  return true;
}
function appearancePresetStore() {
  try {
    const raw = localStorage.getItem('printdirector-appearance-presets') || localStorage.getItem('printdirector-profiles') || '{}';
    return JSON.parse(raw);
  } catch { return {}; }
}
function saveAppearancePresetStore(store) {
  localStorage.setItem('printdirector-appearance-presets', JSON.stringify(store));
  refreshAppearancePresetList();
}
function refreshAppearancePresetList() {
  const select = $('appearance-presets-list');
  const current = select.value;
  const store = appearancePresetStore();
  select.innerHTML = '<option value="">Choose a saved preset</option>';
  Object.keys(store).sort().forEach((name) => {
    const option = document.createElement('option'); option.value = name; option.textContent = name; option.selected = name === current;
    select.appendChild(option);
  });
}
function applyAppearanceValues(values) {
  populateAppearance({ ...appearanceFromControls(), ...values, printer_overrides: overlaySettings.printer_overrides || {} });
  setPageStatus('Appearance preview updated. Save appearance to keep it.');
}

function populateConnections(config) {
  runtimeConfig = config;
  $('obs-host').value = config.obs?.host || '127.0.0.1';
  $('obs-port').value = config.obs?.port || 4455;
  $('obs-password-env').value = config.obs?.password_env || 'OBS_WEBSOCKET_PASSWORD';
  $('obs-password').value = config.obs?.password || '';
  $('overlay-host').value = config.overlay?.host || '127.0.0.1';
  $('overlay-port').value = config.overlay?.port || 8765;
  $('allow-lan').checked = Boolean(config.overlay?.allow_lan);
}
async function saveConnections() {
  const payload = {
    obs: {
      host: $('obs-host').value.trim() || '127.0.0.1', port: Number($('obs-port').value || 4455),
      password_env: $('obs-password-env').value.trim() || 'OBS_WEBSOCKET_PASSWORD',
      password: $('obs-password').value || runtimeConfig.obs?.password || ''
    },
    overlay: { host: $('overlay-host').value.trim() || '127.0.0.1', port: Number($('overlay-port').value || 8765), allow_lan: $('allow-lan').checked }
  };
  setPageStatus('Saving connection settings…');
  const response = await fetch('/api/system-config', {
    method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify(payload)
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) { setPageStatus(data.detail || 'Connection settings save failed.', false); return; }
  runtimeConfig = data;
  populateConnections(data);
  const restart = data.restart_required?.length ? ` Restart required for: ${data.restart_required.join(', ')}.` : '';
  setPageStatus(`Connection settings saved.${restart}`);
}
async function refreshPrinterStatuses() {
  try {
    const response = await fetch('/api/printers', { headers: authHeaders() });
    if (!response.ok) return;
    const statuses = await response.json();
    printerStatuses = Object.fromEntries(statuses.map((status) => [status.printer_id, status]));
  } catch { printerStatuses = {}; }
}

$('settings-nav').addEventListener('click', (event) => {
  const tab = event.target.closest('.settings-tab');
  if (!tab) return;
  event.preventDefault();
  activateSettingsSection(tab.dataset.section);
  history.replaceState(null, '', tab.getAttribute('href'));
});
$('store-api-token').addEventListener('click', () => {
  const token = $('api-token').value.trim();
  if (token) localStorage.setItem('printdirector-token', token); else localStorage.removeItem('printdirector-token');
  setPageStatus(token ? 'API token stored in this browser.' : 'API token cleared.');
});
document.querySelectorAll('[data-appearance-control]').forEach((control) => {
  control.addEventListener('input', renderGlobalPreview); control.addEventListener('change', renderGlobalPreview);
});
document.querySelectorAll('[data-appearance-preset]').forEach((button) => {
  button.addEventListener('click', () => applyAppearanceValues(APPEARANCE_PRESETS[button.dataset.appearancePreset]));
});
$('save-appearance').addEventListener('click', () => saveAppearance().catch((error) => setPageStatus(error.message, false)));
$('reset-appearance').addEventListener('click', () => applyAppearanceValues(APPEARANCE_DEFAULTS));
$('save-appearance-preset').addEventListener('click', () => {
  const name = $('appearance-preset-name').value.trim();
  if (!name) return setPageStatus('Choose a preset name first.', false);
  const store = appearancePresetStore(); const values = appearanceFromControls(); delete values.printer_overrides;
  store[name] = values; saveAppearancePresetStore(store); $('appearance-presets-list').value = name;
  setPageStatus(`Appearance preset “${name}” saved locally.`);
});
$('load-appearance-preset').addEventListener('click', () => {
  const values = appearancePresetStore()[$('appearance-presets-list').value];
  if (!values) return setPageStatus('Choose a saved appearance preset.', false);
  applyAppearanceValues(values);
});
$('delete-appearance-preset').addEventListener('click', () => {
  const name = $('appearance-presets-list').value; if (!name) return;
  const store = appearancePresetStore(); delete store[name]; saveAppearancePresetStore(store); setPageStatus(`Appearance preset “${name}” deleted.`);
});
$('export-appearance-preset').addEventListener('click', () => {
  const values = appearanceFromControls(); delete values.printer_overrides;
  const blob = new Blob([JSON.stringify(values, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob); const link = document.createElement('a');
  link.href = url; link.download = 'printdirector-appearance.json'; link.click(); URL.revokeObjectURL(url);
});
$('import-appearance-preset').addEventListener('change', (event) => {
  const file = event.target.files?.[0]; if (!file) return;
  const reader = new FileReader();
  reader.onload = () => { try { applyAppearanceValues(JSON.parse(String(reader.result))); } catch { setPageStatus('Invalid appearance JSON.', false); } };
  reader.readAsText(file); event.target.value = '';
});
$('save-connections').addEventListener('click', () => saveConnections().catch((error) => setPageStatus(error.message, false)));

async function loadBaseSettings() {
  const [appearanceResponse, runtimeResponse] = await Promise.all([
    fetch('/api/settings', { headers: authHeaders() }), fetch('/api/system-config', { headers: authHeaders() })
  ]);
  if (!appearanceResponse.ok) throw new Error('Unable to load appearance settings.');
  if (!runtimeResponse.ok) throw new Error('Unable to load system configuration.');
  populateAppearance(await appearanceResponse.json());
  populateConnections(await runtimeResponse.json());
  await refreshPrinterStatuses();
  refreshAppearancePresetList();
  const token = getToken(); if (token) $('api-token').value = token;
  setPageStatus('Settings loaded.');
}

const initialSection = location.hash.replace('#settings-', '');
activateSettingsSection(['general', 'connections', 'operations', 'printers'].includes(initialSection) ? initialSection : 'general');
window.printDirectorSettingsReady = loadBaseSettings().catch((error) => { setPageStatus(error.message, false); throw error; });
