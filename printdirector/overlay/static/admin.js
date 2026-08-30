const defaults = {
  theme: 'dark',
  background_color: '#0b0e14',
  text_color: '#f5f7fa',
  accent_color: '#38bdf8',
  panel_opacity: 0.92,
  font_family: 'system-ui',
  font_scale: 1,
  show_filename: true,
  show_state: true,
  show_eta: true,
  show_temps: true,
  show_layers: true,
  printer_overrides: {}
};

const presets = {
  dark: { theme: 'dark', background_color: '#0b0e14', text_color: '#f5f7fa', accent_color: '#38bdf8', panel_opacity: 0.92, font_scale: 1.0 },
  light: { theme: 'light', background_color: '#f8fafc', text_color: '#0f172a', accent_color: '#0ea5e9', panel_opacity: 0.86, font_scale: 1.0 },
  mint: { theme: 'dark', background_color: '#071b16', text_color: '#e6fffb', accent_color: '#34d399', panel_opacity: 0.9, font_scale: 1.08 },
  sunset: { theme: 'dark', background_color: '#1f0c12', text_color: '#fff1f2', accent_color: '#f97316', panel_opacity: 0.88, font_scale: 1.08 }
};

const form = document.getElementById('settings-form');
const statusEl = document.getElementById('status');
const previewCard = document.getElementById('preview-card');
const resetButton = document.getElementById('reset-settings');
const profileNameInput = document.getElementById('profile-name');
const profilesList = document.getElementById('profiles-list');
const saveProfileButton = document.getElementById('save-profile');
const loadProfileButton = document.getElementById('load-profile');
const deleteProfileButton = document.getElementById('delete-profile');
const exportProfileButton = document.getElementById('export-profile');
const importProfileInput = document.getElementById('import-profile');
const tokenInput = document.getElementById('api-token');
const tokenSaveButton = document.getElementById('token-save');
const printerSelect = document.getElementById('printer-override-select');
const printerPages = document.getElementById('printer-pages');
const selectedPrinterTitle = document.getElementById('selected-printer-title');
const selectedPrinterId = document.getElementById('selected-printer-id');
const savePrinterStyleButton = document.getElementById('save-printer-style');
const applyStyleTarget = document.getElementById('apply-style-target');
const applyPrinterStyleButton = document.getElementById('apply-printer-style');
const printerIdInput = document.getElementById('printer-id');
const printerNameInput = document.getElementById('printer-name');
const printerSceneInput = document.getElementById('printer-scene');
const printerLabelInput = document.getElementById('printer-label-override');
const printerTypeInput = document.getElementById('printer-type');
const printerMoonrakerInput = document.getElementById('printer-moonraker-url');
const printerBambuInput = document.getElementById('printer-bambu-url');
const printerAccessCodeInput = document.getElementById('printer-access-code');
const printerSerialInput = document.getElementById('printer-serial-number');
const printerAccentInput = document.getElementById('printer-accent-color');
const printerTextInput = document.getElementById('printer-text-color');
const printerOpacityInput = document.getElementById('printer-panel-opacity');
const printerShowFilename = document.getElementById('printer-show-filename');
const printerShowState = document.getElementById('printer-show-state');
const printerShowEta = document.getElementById('printer-show-eta');
const printerShowTemps = document.getElementById('printer-show-temps');
const printerShowLayers = document.getElementById('printer-show-layers');
const clearPrinterOverrideButton = document.getElementById('clear-printer-override');
const saveSystemButton = document.getElementById('save-system-config');
const addPrinterButton = document.getElementById('add-printer');
const removePrinterButton = document.getElementById('remove-printer');
const testPrinterButton = document.getElementById('test-printer');
const obsHostInput = document.getElementById('obs-host');
const obsPortInput = document.getElementById('obs-port');
const obsPasswordEnvInput = document.getElementById('obs-password-env');
const obsPasswordInput = document.getElementById('obs-password');
const overlayHostInput = document.getElementById('overlay-host');
const overlayPortInput = document.getElementById('overlay-port');
const allowLanInput = document.getElementById('allow-lan');

let currentSettings = { ...defaults };
let currentRuntimeConfig = { printers: [], obs: {}, overlay: {}, auth: {} };

function activateSettingsSection(section) {
  document.querySelectorAll('.settings-tab').forEach((button) => {
    const active = button.dataset.section === section;
    button.classList.toggle('active', active);
    button.setAttribute('aria-selected', String(active));
  });
  document.querySelectorAll('[data-settings-section]').forEach((panel) => {
    panel.hidden = panel.dataset.settingsSection !== section;
  });
}

document.querySelectorAll('.settings-tab').forEach((button) => {
  button.addEventListener('click', () => activateSettingsSection(button.dataset.section));
});
activateSettingsSection('general');

function getToken() {
  const fromStorage = localStorage.getItem('printdirector-token');
  if (fromStorage) return fromStorage.trim();
  const fromQuery = new URLSearchParams(window.location.search).get('token');
  return fromQuery ? fromQuery.trim() : null;
}

function setToken(token) {
  if (!token) {
    localStorage.removeItem('printdirector-token');
    return;
  }
  localStorage.setItem('printdirector-token', token.trim());
}

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function setStatus(message, ok = true, timestamp = null) {
  statusEl.textContent = timestamp ? `${message} • ${timestamp}` : message;
  statusEl.style.color = ok ? '#86efac' : '#fca5a5';
}

function stamp() {
  const now = new Date();
  return now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function getProfiles() {
  try {
    return JSON.parse(localStorage.getItem('printdirector-profiles') || '{}');
  } catch {
    return {};
  }
}

function persistProfiles(profiles) {
  localStorage.setItem('printdirector-profiles', JSON.stringify(profiles));
  refreshProfileList();
}

function refreshProfileList() {
  const profiles = getProfiles();
  const currentValue = profilesList.value;
  profilesList.innerHTML = '<option value="">Choose a saved profile</option>';
  Object.keys(profiles).forEach((name) => {
    const option = document.createElement('option');
    option.value = name;
    option.textContent = name;
    if (name === currentValue) option.selected = true;
    profilesList.appendChild(option);
  });
}

function readForm() {
  const data = Object.fromEntries(new FormData(form).entries());
  return {
    ...defaults,
    ...data,
    panel_opacity: Number(data.panel_opacity ?? defaults.panel_opacity),
    font_scale: Number(data.font_scale ?? defaults.font_scale),
    show_filename: form.querySelector('[name="show_filename"]').checked,
    show_state: form.querySelector('[name="show_state"]').checked,
    show_eta: form.querySelector('[name="show_eta"]').checked,
    show_temps: form.querySelector('[name="show_temps"]').checked,
    show_layers: form.querySelector('[name="show_layers"]').checked,
    theme: data.theme || defaults.theme,
    printer_overrides: currentSettings.printer_overrides || {}
  };
}

function populatePrinterSelect(printerIds = []) {
  const selected = printerSelect.value;
  printerSelect.innerHTML = '<option value="">Select a printer</option>';
  printerIds.forEach((printerId) => {
    const option = document.createElement('option');
    option.value = printerId;
    option.textContent = printerId;
    if (printerId === selected) option.selected = true;
    printerSelect.appendChild(option);
  });
  if (!printerSelect.value && printerIds.length) printerSelect.value = printerIds[0];
  const printers = currentRuntimeConfig.printers || [];
  printerPages.innerHTML = '';
  printers.forEach((printer) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'printer-page-button';
    button.dataset.printerId = printer.id;
    button.innerHTML = `<strong>${escapeHtml(printer.name || printer.id)}</strong><small>${escapeHtml(printer.id)}</small>`;
    button.addEventListener('click', () => {
      printerSelect.value = printer.id;
      syncPrinterInputsForSelectedPrinter();
      applyPrinterOverrideControls(currentSettings, printer.id);
      updateSelectedPrinterUI();
    });
    printerPages.appendChild(button);
  });
  applyStyleTarget.innerHTML = '<option value="">Apply saved style to…</option>';
  printers.forEach((printer) => {
    const option = document.createElement('option');
    option.value = printer.id;
    option.textContent = printer.name || printer.id;
    applyStyleTarget.appendChild(option);
  });
  updateSelectedPrinterUI();
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[character]));
}

function updateSelectedPrinterUI() {
  const printer = (currentRuntimeConfig.printers || []).find((entry) => entry.id === printerSelect.value);
  selectedPrinterTitle.textContent = printer ? (printer.name || printer.id) : 'No printer selected';
  selectedPrinterId.textContent = printer ? `ID: ${printer.id}` : '';
  document.querySelectorAll('.printer-page-button').forEach((button) => {
    button.classList.toggle('active', button.dataset.printerId === printerSelect.value);
  });
}

function syncPrinterInputsForSelectedPrinter() {
  const pid = printerSelect.value;
  if (!pid || !Array.isArray(currentRuntimeConfig.printers)) return;
  const printer = currentRuntimeConfig.printers.find((entry) => entry.id === pid) || currentRuntimeConfig.printers[0];
  if (!printer) return;
  printerIdInput.value = printer.id || '';
  printerNameInput.value = printer.name || '';
  printerSceneInput.value = printer.obs?.scene || '';
  printerTypeInput.value = printer.type || 'klipper';
  printerMoonrakerInput.value = printer.moonraker_url || '';
  printerBambuInput.value = printer.bambu_url || '';
  printerAccessCodeInput.value = printer.access_code || '';
  printerSerialInput.value = printer.serial_number || '';
}

function readRuntimeConfig() {
  const pid = printerSelect.value;
  let printers = Array.isArray(currentRuntimeConfig.printers)
    ? currentRuntimeConfig.printers.map((printer) => ({ ...printer }))
    : [];
  if (pid) {
    const index = printers.findIndex((printer) => printer.id === pid);
    if (index >= 0) {
      printers[index] = {
        ...printers[index],
        id: printerIdInput.value.trim() || pid,
        name: printerNameInput.value.trim() || printers[index].name || pid,
        type: printerTypeInput.value || printers[index].type || 'klipper',
        moonraker_url: printerMoonrakerInput.value.trim() || null,
        bambu_url: printerBambuInput.value.trim() || null,
        access_code: printerAccessCodeInput.value.trim() || null,
        serial_number: printerSerialInput.value.trim() || null,
        obs: { ...(printers[index].obs || {}), scene: printerSceneInput.value.trim() || printers[index].obs?.scene || 'Printer' }
      };
    } else {
      printers.unshift({
        id: printerIdInput.value.trim() || pid,
        name: printerNameInput.value.trim() || pid,
        type: printerTypeInput.value || 'klipper',
        moonraker_url: printerMoonrakerInput.value.trim() || null,
        bambu_url: printerBambuInput.value.trim() || null,
        access_code: printerAccessCodeInput.value.trim() || null,
        serial_number: printerSerialInput.value.trim() || null,
        obs: { scene: printerSceneInput.value.trim() || 'Printer' }
      });
    }
  }
  return {
    obs: {
      host: obsHostInput.value.trim() || '127.0.0.1',
      port: Number(obsPortInput.value || 4455),
      password_env: obsPasswordEnvInput.value.trim() || 'OBS_WEBSOCKET_PASSWORD',
      password: obsPasswordInput.value || currentRuntimeConfig.obs?.password || ''
    },
    overlay: {
      host: overlayHostInput.value.trim() || '127.0.0.1',
      port: Number(overlayPortInput.value || 8765),
      allow_lan: allowLanInput.checked,
      settings_file: currentRuntimeConfig.overlay?.settings_file || 'overlay-settings.json'
    },
    auth: {
      enabled: currentRuntimeConfig.auth?.enabled ?? false,
      token_env: currentRuntimeConfig.auth?.token_env || 'PRINTDIRECTOR_TOKEN',
      token: currentRuntimeConfig.auth?.token || ''
    },
    printers
  };
}

function applyRuntimeConfig(config) {
  currentRuntimeConfig = {
    obs: config.obs || {},
    overlay: config.overlay || {},
    auth: config.auth || {},
    printers: Array.isArray(config.printers) ? config.printers : []
  };
  if (!currentRuntimeConfig.printers.length) {
    currentRuntimeConfig.printers = [{ id: 'printer-1', name: 'Printer 1', type: 'klipper', obs: { scene: 'Printer 1' } }];
  }
  obsHostInput.value = currentRuntimeConfig.obs.host || '127.0.0.1';
  obsPortInput.value = currentRuntimeConfig.obs.port || 4455;
  obsPasswordEnvInput.value = currentRuntimeConfig.obs.password_env || 'OBS_WEBSOCKET_PASSWORD';
  obsPasswordInput.value = currentRuntimeConfig.obs.password || '';
  overlayHostInput.value = currentRuntimeConfig.overlay.host || '127.0.0.1';
  overlayPortInput.value = currentRuntimeConfig.overlay.port || 8765;
  allowLanInput.checked = Boolean(currentRuntimeConfig.overlay.allow_lan);
  populatePrinterSelect(currentRuntimeConfig.printers.map((printer) => printer.id));
  if (!printerSelect.value && currentRuntimeConfig.printers.length) printerSelect.value = currentRuntimeConfig.printers[0].id;
  syncPrinterInputsForSelectedPrinter();
  updateSelectedPrinterUI();
}

async function loadRuntimeConfig() {
  const response = await fetch('/api/system-config', { headers: authHeaders() });
  if (!response.ok) return;
  const config = await response.json();
  applyRuntimeConfig(config);
}

async function saveRuntimeConfig() {
  const payload = readRuntimeConfig();
  const response = await fetch('/api/system-config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    const error = await response.text();
    setStatus(`System config save failed: ${error}`, false);
    return;
  }
  const config = await response.json();
  applyRuntimeConfig(config);
  setStatus('System configuration saved.', true, stamp());
}

function applyPrinterOverrideControls(settings, pid) {
  const override = (settings.printer_overrides && settings.printer_overrides[pid]) || {};
  printerLabelInput.value = override.label_override || '';
  printerAccentInput.value = override.accent_color || settings.accent_color || defaults.accent_color;
  printerTextInput.value = override.text_color || settings.text_color || defaults.text_color;
  printerOpacityInput.value = String(override.panel_opacity ?? settings.panel_opacity ?? defaults.panel_opacity);
  printerShowFilename.checked = override.show_filename ?? settings.show_filename ?? defaults.show_filename;
  printerShowState.checked = override.show_state ?? settings.show_state ?? defaults.show_state;
  printerShowEta.checked = override.show_eta ?? settings.show_eta ?? defaults.show_eta;
  printerShowTemps.checked = override.show_temps ?? settings.show_temps ?? defaults.show_temps;
  printerShowLayers.checked = override.show_layers ?? settings.show_layers ?? defaults.show_layers;
}

function readPrinterOverride() {
  const pid = printerSelect.value;
  if (!pid) return null;
  return {
    pid,
    override: {
      accent_color: printerAccentInput.value,
      text_color: printerTextInput.value,
      panel_opacity: Number(printerOpacityInput.value),
      show_filename: printerShowFilename.checked,
      show_state: printerShowState.checked,
      show_eta: printerShowEta.checked,
      show_temps: printerShowTemps.checked,
      show_layers: printerShowLayers.checked,
      label_override: printerLabelInput.value.trim()
    }
  };
}

function applySettings(settings) {
  const root = previewCard;
  const theme = settings.theme || defaults.theme;
  const accent = settings.accent_color || defaults.accent_color;
  const text = settings.text_color || defaults.text_color;
  const panelOpacity = Number(settings.panel_opacity ?? defaults.panel_opacity);
  const fontFamily = settings.font_family || defaults.font_family;
  const fontScale = Number(settings.font_scale ?? defaults.font_scale);

  root.style.setProperty('--accent', accent);
  root.style.background = theme === 'light' ? `rgba(255, 255, 255, ${panelOpacity})` : `rgba(13, 18, 28, ${panelOpacity})`;
  root.style.color = text;
  root.style.fontFamily = fontFamily;
  root.style.fontSize = `${fontScale.toFixed(2)}rem`;
  root.style.borderColor = accent;
  root.style.boxShadow = `0 18px 40px ${theme === 'light' ? 'rgba(15, 23, 42, 0.16)' : 'rgba(0,0,0,0.25)'}`;

  const fileRow = root.querySelector('.file');
  const stateRow = root.querySelector('.state');
  const previewHeader = root.querySelector('.preview-header');
  const metaRows = root.querySelectorAll('.meta');
  const etaRow = metaRows[0];
  const tempRow = metaRows[1];
  const layerRow = root.querySelector('.preview-actions');

  if (fileRow) fileRow.style.display = settings.show_filename ? 'block' : 'none';
  if (stateRow) stateRow.style.display = settings.show_state ? 'inline' : 'none';
  if (etaRow) etaRow.style.display = settings.show_eta ? 'flex' : 'none';
  if (tempRow) tempRow.style.display = settings.show_temps ? 'flex' : 'none';
  if (layerRow) layerRow.style.display = settings.show_layers ? 'flex' : 'none';
  if (previewHeader) previewHeader.style.color = text;
  document.body.style.background = theme === 'light'
    ? 'linear-gradient(180deg, rgba(148,163,184,0.12), rgba(248,250,252,1))'
    : 'radial-gradient(circle at top, rgba(56, 189, 248, 0.12), transparent 30%), #020817';
}

function populateForm(settings) {
  currentSettings = { ...defaults, ...settings, printer_overrides: settings.printer_overrides || {} };
  Object.entries(settings).forEach(([key, value]) => {
    if (key === 'printer_overrides' || key === 'printer_ids') return;
    const field = form.elements.namedItem(key);
    if (!field) return;
    if (field.type === 'checkbox') {
      field.checked = Boolean(value);
    } else {
      field.value = value;
    }
  });

  const activePreset = Object.keys(presets).find((name) => {
    const preset = presets[name];
    return preset.theme === settings.theme && preset.background_color === settings.background_color && preset.text_color === settings.text_color && preset.accent_color === settings.accent_color;
  });
  document.querySelectorAll('.preset-btn').forEach((button) => {
    button.classList.toggle('active', button.dataset.preset === activePreset);
  });

  if (settings.printer_ids) populatePrinterSelect(settings.printer_ids);
  const selectedPrinter = printerSelect.value || (settings.printer_ids && settings.printer_ids[0]) || '';
  if (selectedPrinter) {
    printerSelect.value = selectedPrinter;
    applyPrinterOverrideControls(currentSettings, selectedPrinter);
  }
  applySettings(currentSettings);
}

function loadProfileData(name) {
  const profiles = getProfiles();
  const profile = profiles[name];
  if (!profile) return null;
  const merged = { ...defaults, ...profile };
  populateForm(merged);
  return merged;
}

function buildPayload() {
  const payload = readForm();
  const selected = readPrinterOverride();
  if (selected) {
    payload.printer_overrides = { ...(currentSettings.printer_overrides || {}) };
    if (Object.values(selected.override).some((value) => value !== '' && value !== false && value !== null)) {
      payload.printer_overrides[selected.pid] = selected.override;
    } else {
      delete payload.printer_overrides[selected.pid];
    }
  }
  delete payload.printer_ids;
  return payload;
}

async function loadSettings() {
  const response = await fetch('/api/settings', { headers: authHeaders() });
  if (!response.ok) throw new Error('Unable to load settings');
  const settings = await response.json();
  populateForm({ ...defaults, ...settings, printer_overrides: settings.printer_overrides || {} });
  await loadRuntimeConfig();
}

document.querySelectorAll('.preset-btn').forEach((button) => {
  button.addEventListener('click', () => {
    const preset = presets[button.dataset.preset];
    if (!preset) return;
    const values = { ...defaults, ...readForm(), ...preset };
    populateForm(values);
    setStatus('Preset applied • live preview', true, stamp());
  });
});

addPrinterButton.addEventListener('click', () => {
  const nextNumber = (currentRuntimeConfig.printers || []).length + 1;
  const nextId = `printer-${nextNumber}`;
  const printer = {
    id: nextId,
    name: `Printer ${nextNumber}`,
    type: 'klipper',
    moonraker_url: '',
    obs: { scene: `Printer ${nextNumber}` }
  };
  currentRuntimeConfig.printers = [...(currentRuntimeConfig.printers || []), printer];
  populatePrinterSelect(currentRuntimeConfig.printers.map((entry) => entry.id));
  printerSelect.value = nextId;
  syncPrinterInputsForSelectedPrinter();
  updateSelectedPrinterUI();
  setStatus(`Added ${nextId}. Save system config to keep it.`, true, stamp());
});

async function testSelectedPrinter() {
  const pid = printerSelect.value;
  if (!pid) {
    setStatus('Select a printer before testing the connection.', false);
    return;
  }
  const printer = {
    id: printerIdInput.value.trim() || pid,
    name: printerNameInput.value.trim() || pid,
    type: printerTypeInput.value || 'klipper',
    moonraker_url: printerMoonrakerInput.value.trim() || null,
    bambu_url: printerBambuInput.value.trim() || null,
    access_code: printerAccessCodeInput.value.trim() || null,
    serial_number: printerSerialInput.value.trim() || null,
    obs: { scene: printerSceneInput.value.trim() || printerNameInput.value.trim() || pid }
  };
  setStatus('Testing printer connection…');
  const response = await fetch('/api/printers/test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ printer })
  });
  const text = await response.text();
  let data = {};
  try { data = JSON.parse(text); } catch (error) { data = {}; }
  if (!response.ok) {
    setStatus(data.detail || text || 'Printer connection failed.', false);
    return;
  }
  setStatus(data.message || 'Printer connection successful.', true, stamp());
}

removePrinterButton.addEventListener('click', () => {
  const pid = printerSelect.value;
  if (!pid) return;
  const remaining = (currentRuntimeConfig.printers || []).filter((printer) => printer.id !== pid);
  if (!remaining.length) {
    setStatus('At least one printer is required.', false);
    return;
  }
  currentRuntimeConfig.printers = remaining;
  populatePrinterSelect(currentRuntimeConfig.printers.map((entry) => entry.id));
  printerSelect.value = currentRuntimeConfig.printers[0].id;
  syncPrinterInputsForSelectedPrinter();
  setStatus(`Removed ${pid}. Save system config to keep it.`, true, stamp());
});

form.addEventListener('input', () => {
  const values = readForm();
  populateForm(values);
  setStatus('Preview updated', true, stamp());
});

printerSelect.addEventListener('change', () => {
  const selected = printerSelect.value;
  if (!selected) return;
  applyPrinterOverrideControls(currentSettings, selected);
  syncPrinterInputsForSelectedPrinter();
  updateSelectedPrinterUI();
});

savePrinterStyleButton.addEventListener('click', () => {
  const selected = readPrinterOverride();
  if (!selected) {
    setStatus('Select a printer before saving its style.', false);
    return;
  }
  localStorage.setItem('printdirector-printer-style', JSON.stringify(selected.override));
  setStatus(`Saved style from ${selected.pid}.`, true, stamp());
});

applyPrinterStyleButton.addEventListener('click', () => {
  const target = applyStyleTarget.value;
  const source = localStorage.getItem('printdirector-printer-style');
  if (!target || !source) {
    setStatus('Save a printer style and choose a target printer first.', false);
    return;
  }
  const overrideMap = { ...(currentSettings.printer_overrides || {}) };
  overrideMap[target] = JSON.parse(source);
  currentSettings.printer_overrides = overrideMap;
  if (target === printerSelect.value) applyPrinterOverrideControls(currentSettings, target);
  setStatus(`Applied saved style to ${target}. Save overlay settings to keep it.`, true, stamp());
});

saveSystemButton.addEventListener('click', async () => {
  await saveRuntimeConfig();
});

testPrinterButton.addEventListener('click', async () => {
  await testSelectedPrinter();
});

clearPrinterOverrideButton.addEventListener('click', () => {
  const pid = printerSelect.value;
  if (!pid) return;
  const overrideMap = { ...(currentSettings.printer_overrides || {}) };
  delete overrideMap[pid];
  currentSettings.printer_overrides = overrideMap;
  applyPrinterOverrideControls({ ...currentSettings, printer_overrides: overrideMap }, pid);
  setStatus(`Cleared override for ${pid}.`, true, stamp());
});

tokenSaveButton.addEventListener('click', () => {
  const token = tokenInput.value.trim();
  setToken(token);
  if (!token) {
    setStatus('Token cleared from local storage.', true, stamp());
    return;
  }
  setStatus('Token stored locally for this browser.', true, stamp());
});

saveProfileButton.addEventListener('click', () => {
  const name = profileNameInput.value.trim();
  if (!name) {
    setStatus('Choose a profile name first.', false);
    return;
  }
  const profiles = getProfiles();
  profiles[name] = buildPayload();
  persistProfiles(profiles);
  setStatus(`Profile saved: ${name}`, true, stamp());
});

loadProfileButton.addEventListener('click', () => {
  const name = profilesList.value;
  if (!name) {
    setStatus('Choose a saved profile first.', false);
    return;
  }
  const profile = loadProfileData(name);
  if (profile) setStatus(`Loaded profile: ${name}`, true, stamp());
});

deleteProfileButton.addEventListener('click', () => {
  const name = profilesList.value;
  if (!name) {
    setStatus('Choose a profile to delete.', false);
    return;
  }
  const profiles = getProfiles();
  delete profiles[name];
  persistProfiles(profiles);
  profileNameInput.value = '';
  setStatus(`Deleted profile: ${name}`, true, stamp());
});

exportProfileButton.addEventListener('click', () => {
  const profile = buildPayload();
  const blob = new Blob([JSON.stringify(profile, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'printdirector-overlay.json';
  link.click();
  URL.revokeObjectURL(url);
  setStatus('Profile exported as JSON', true, stamp());
});

importProfileInput.addEventListener('change', (event) => {
  const file = event.target.files && event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const data = JSON.parse(String(reader.result));
      populateForm({ ...defaults, ...data, printer_overrides: data.printer_overrides || {} });
      setStatus('Profile imported from JSON', true, stamp());
    } catch (error) {
      setStatus('Invalid JSON import.', false);
    }
  };
  reader.readAsText(file);
  event.target.value = '';
});

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const payload = buildPayload();
  setStatus('Saving overlay settings…');
  const response = await fetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    const error = await response.text();
    setStatus(`Save failed: ${error}`, false);
    return;
  }

  const settings = await response.json();
  populateForm({ ...defaults, ...settings, printer_overrides: settings.printer_overrides || {} });
  setStatus('Settings saved.', true, stamp());
});

resetButton.addEventListener('click', () => {
  populateForm({ ...defaults, printer_overrides: {} });
  setStatus('Defaults restored locally. Save to keep them.', true, stamp());
});

refreshProfileList();
if (getToken()) tokenInput.value = getToken();
loadSettings().catch((error) => {
  setStatus(error.message || 'Unable to load settings', false);
});
