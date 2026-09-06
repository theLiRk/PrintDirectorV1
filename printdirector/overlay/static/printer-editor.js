let printerDrafts = new Map();
let activeDraftKey = null;
let newPrinterCounter = 0;
let suppressPrinterInput = false;

function activatePrinterSection(section) {
  document.querySelectorAll('[data-printer-tab]').forEach((tab) => tab.classList.toggle('active', tab.dataset.printerTab === section));
  document.querySelectorAll('[data-printer-section]').forEach((panel) => { panel.hidden = panel.dataset.printerSection !== section; });
}
function makeSavedDraft(printer) {
  const override = overlaySettings.printer_overrides?.[printer.id];
  return {
    key: `saved:${printer.id}`, originalId: printer.id, isNew: false, dirty: false,
    printer: deepClone(printer), customOverlay: Boolean(override), overlayOverride: override ? deepClone(override) : {}
  };
}
function initializePrinterDrafts(preferredId = null) {
  printerDrafts = new Map();
  (runtimeConfig.printers || []).forEach((printer) => { const draft = makeSavedDraft(printer); printerDrafts.set(draft.key, draft); });
  const preferredKey = preferredId ? `saved:${preferredId}` : null;
  activeDraftKey = preferredKey && printerDrafts.has(preferredKey) ? preferredKey : (printerDrafts.keys().next().value || null);
  renderPrinterList(); renderPrinterEditor();
}
function activeDraft() { return activeDraftKey ? printerDrafts.get(activeDraftKey) : null; }
function connectionLabel(draft) {
  if (draft.isNew) return 'Not saved';
  const status = printerStatuses[draft.originalId];
  if (!status) return 'Unknown';
  if (status.stale) return 'Stale';
  return status.online ? 'Connected' : 'Offline';
}
function connectionState(draft) {
  if (draft.isNew) return 'neutral';
  const status = printerStatuses[draft.originalId];
  if (!status) return 'neutral';
  if (status.stale) return 'warning';
  return status.online ? 'ok' : 'error';
}
function renderPrinterList() {
  const list = $('printer-list'); list.innerHTML = '';
  printerDrafts.forEach((draft, key) => {
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'printer-list-item'; button.classList.toggle('active', key === activeDraftKey);
    const main = document.createElement('span'); main.className = 'printer-list-main';
    const title = document.createElement('strong'); title.textContent = draft.printer.name || 'Unnamed printer';
    const id = document.createElement('small'); id.textContent = draft.printer.id || 'No ID'; main.append(title, id);
    const meta = document.createElement('span'); meta.className = 'printer-list-meta';
    if (draft.dirty) { const dirty = document.createElement('span'); dirty.className = 'pill warning'; dirty.textContent = 'Unsaved'; meta.appendChild(dirty); }
    const status = document.createElement('span'); status.className = `connection-dot ${connectionState(draft)}`; status.title = connectionLabel(draft); meta.appendChild(status);
    button.append(main, meta); button.addEventListener('click', () => switchPrinter(key)); list.appendChild(button);
  });
  $('printer-empty-state').hidden = printerDrafts.size > 0;
}
function switchPrinter(key) {
  if (key === activeDraftKey || !printerDrafts.has(key)) return;
  captureActiveDraft(false);
  activeDraftKey = key;
  renderPrinterList(); renderPrinterEditor();
}
function uniqueNewPrinterId() {
  const used = new Set([...printerDrafts.values()].map((draft) => draft.printer.id));
  let candidate;
  do { newPrinterCounter += 1; candidate = `printer-${newPrinterCounter}`; } while (used.has(candidate));
  return candidate;
}
function addPrinterDraft() {
  captureActiveDraft(false);
  const id = uniqueNewPrinterId(); const key = `new:${Date.now()}:${newPrinterCounter}`;
  printerDrafts.set(key, {
    key, originalId: null, isNew: true, dirty: true,
    printer: { id, name: 'New printer', type: 'klipper', moonraker_url: '', bambu_url: null, access_code: null, serial_number: null, obs: { scene: `Printer - ${id}` } },
    customOverlay: false, overlayOverride: {}
  });
  activeDraftKey = key; renderPrinterList(); renderPrinterEditor(); activatePrinterSection('connection');
  setPageStatus('New printer draft created. It is not saved yet.');
}
function readPrinterFields(draft) {
  const type = $('printer-type').value || 'klipper';
  draft.printer = {
    ...draft.printer, id: $('printer-id').value.trim(), name: $('printer-name').value.trim(), type,
    // Keep inactive adapter fields in the draft so toggling type does not erase work.
    moonraker_url: $('printer-moonraker-url').value.trim() || null,
    bambu_url: $('printer-bambu-url').value.trim() || null,
    access_code: $('printer-access-code').value.trim() || null,
    serial_number: $('printer-serial-number').value.trim() || null,
    obs: { ...(draft.printer.obs || {}), scene: $('printer-scene').value.trim() }
  };
  draft.customOverlay = $('printer-custom-overlay').checked;
  if (draft.customOverlay) {
    draft.overlayOverride = {
      accent_color: $('printer-accent-color').value, text_color: $('printer-text-color').value,
      panel_opacity: Number($('printer-panel-opacity').value), font_scale: Number($('printer-font-scale').value),
      show_filename: $('printer-show-filename').checked, show_state: $('printer-show-state').checked,
      show_eta: $('printer-show-eta').checked, show_temps: $('printer-show-temps').checked,
      show_layers: $('printer-show-layers').checked, label_override: $('printer-label-override').value.trim() || null
    };
  }
}
function captureActiveDraft(markDirty = true) {
  const draft = activeDraft(); if (!draft || suppressPrinterInput) return;
  readPrinterFields(draft); if (markDirty) draft.dirty = true;
}
function seedCustomOverlay(draft) {
  if (Object.keys(draft.overlayOverride || {}).length) return;
  draft.overlayOverride = {
    accent_color: overlaySettings.accent_color, text_color: overlaySettings.text_color,
    panel_opacity: overlaySettings.panel_opacity, font_scale: overlaySettings.font_scale,
    show_filename: overlaySettings.show_filename, show_state: overlaySettings.show_state, show_eta: overlaySettings.show_eta,
    show_temps: overlaySettings.show_temps, show_layers: overlaySettings.show_layers, label_override: null
  };
}
function renderPrinterEditor() {
  const draft = activeDraft(); $('printer-editor').hidden = !draft;
  if (!draft) { $('printer-empty-state').hidden = false; return; }
  suppressPrinterInput = true;
  try {
    $('selected-printer-title').textContent = draft.printer.name || 'Unnamed printer';
    $('selected-printer-connectivity').textContent = connectionLabel(draft);
    $('selected-printer-connectivity').dataset.state = connectionState(draft);
    $('selected-printer-dirty').hidden = !draft.dirty;
    $('printer-name').value = draft.printer.name || ''; $('printer-id').value = draft.printer.id || '';
    $('printer-type').value = draft.printer.type || 'klipper'; $('printer-moonraker-url').value = draft.printer.moonraker_url || '';
    $('printer-bambu-url').value = draft.printer.bambu_url || ''; $('printer-access-code').value = draft.printer.access_code || '';
    $('printer-serial-number').value = draft.printer.serial_number || ''; $('printer-scene').value = draft.printer.obs?.scene || '';
    $('printer-custom-overlay').checked = draft.customOverlay;
    if (draft.customOverlay) seedCustomOverlay(draft);
    const override = draft.overlayOverride || {};
    $('printer-label-override').value = override.label_override || '';
    $('printer-accent-color').value = override.accent_color || overlaySettings.accent_color;
    $('printer-text-color').value = override.text_color || overlaySettings.text_color;
    $('printer-panel-opacity').value = String(override.panel_opacity ?? overlaySettings.panel_opacity);
    $('printer-font-scale').value = String(override.font_scale ?? overlaySettings.font_scale);
    $('printer-show-filename').checked = override.show_filename ?? overlaySettings.show_filename;
    $('printer-show-state').checked = override.show_state ?? overlaySettings.show_state;
    $('printer-show-eta').checked = override.show_eta ?? overlaySettings.show_eta;
    $('printer-show-temps').checked = override.show_temps ?? overlaySettings.show_temps;
    $('printer-show-layers').checked = override.show_layers ?? overlaySettings.show_layers;
    updatePrinterTypeFields(); updateCustomOverlayControls(); renderPrinterPreview();
    $('save-printer').disabled = !draft.dirty; $('discard-printer-changes').disabled = !draft.dirty;
    $('delete-printer').textContent = draft.isNew ? 'Discard new printer' : 'Delete printer';
  } finally { suppressPrinterInput = false; }
}
function updatePrinterTypeFields() {
  const bambu = $('printer-type').value === 'bambu'; $('klipper-settings').hidden = bambu; $('bambu-settings').hidden = !bambu;
}
function updateCustomOverlayControls() {
  const enabled = $('printer-custom-overlay').checked;
  document.querySelectorAll('[data-printer-overlay-control]').forEach((control) => { control.disabled = !enabled; });
  $('printer-overlay-mode-label').textContent = enabled ? 'Custom appearance' : 'Using global appearance';
}
function resolvedPrinterAppearance(draft) { return draft.customOverlay ? { ...overlaySettings, ...(draft.overlayOverride || {}) } : { ...overlaySettings }; }
function renderPrinterPreview() {
  const draft = activeDraft(); if (!draft) return;
  captureActiveDraft(false);
  applyCardPreview($('printer-preview-card'), resolvedPrinterAppearance(draft), draft.printer.name || 'Printer preview');
}
function validatePrinterDraft(draft) {
  const printer = draft.printer;
  if (!printer.name.trim()) return 'Printer name is required.';
  if (!/^[a-zA-Z0-9_-]+$/.test(printer.id)) return 'Printer ID may only contain letters, numbers, hyphens and underscores.';
  const duplicate = [...printerDrafts.values()].find((other) => other.key !== draft.key && other.printer.id === printer.id);
  if (duplicate) return `Printer ID “${printer.id}” is already used by ${duplicate.printer.name || 'another printer'}.`;
  if (!printer.obs?.scene?.trim()) return 'OBS scene is required.';
  if (printer.type === 'bambu') {
    if (!printer.bambu_url) return 'Bambu MQTT URL is required.';
    if (!printer.access_code) return 'Bambu access code is required.';
    if (!printer.serial_number) return 'Bambu serial number is required.';
  } else if (!printer.moonraker_url) return 'Moonraker URL is required.';
  return null;
}
function printerForPersistence(printer) {
  const clean = deepClone(printer);
  if (clean.type === 'bambu') clean.moonraker_url = null;
  else { clean.bambu_url = null; clean.access_code = null; clean.serial_number = null; }
  return clean;
}
function persistedPrintersWithDraft(draft) {
  const printers = (runtimeConfig.printers || []).map((printer) => deepClone(printer));
  if (draft.isNew) { printers.push(printerForPersistence(draft.printer)); return printers; }
  const index = printers.findIndex((printer) => printer.id === draft.originalId);
  if (index < 0) throw new Error(`Original printer ${draft.originalId} no longer exists.`);
  printers[index] = printerForPersistence(draft.printer); return printers;
}

async function savePrinterDraft() {
  const draft = activeDraft(); if (!draft) return;
  captureActiveDraft(false);
  const validationError = validatePrinterDraft(draft);
  if (validationError) { $('printer-save-status').textContent = validationError; $('printer-save-status').dataset.state = 'error'; return; }
  $('printer-save-status').textContent = 'Saving printer…'; $('printer-save-status').dataset.state = 'working'; $('save-printer').disabled = true;
  const originalId = draft.originalId; const newId = draft.printer.id;
  try {
    const systemResponse = await fetch('/api/system-config', {
      method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ printers: persistedPrintersWithDraft(draft) })
    });
    const systemData = await systemResponse.json().catch(() => ({}));
    if (!systemResponse.ok) throw new Error(systemData.detail || 'Printer configuration save failed.');
    runtimeConfig = systemData; draft.originalId = newId; draft.isNew = false;

    const overrides = { ...(overlaySettings.printer_overrides || {}) };
    if (originalId && originalId !== newId) delete overrides[originalId];
    if (draft.customOverlay) overrides[newId] = deepClone(draft.overlayOverride); else delete overrides[newId];
    const appearanceResponse = await fetch('/api/settings', {
      method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ ...overlaySettings, printer_overrides: overrides })
    });
    const appearanceData = await appearanceResponse.json().catch(() => ({}));
    if (!appearanceResponse.ok) throw new Error(`Printer connection was saved, but overlay appearance failed: ${appearanceData.detail || 'unknown error'}`);
    overlaySettings = { ...APPEARANCE_DEFAULTS, ...appearanceData, printer_overrides: appearanceData.printer_overrides || {} };

    const persisted = runtimeConfig.printers.find((printer) => printer.id === newId);
    const newDraft = makeSavedDraft(persisted);
    const entries = [...printerDrafts.entries()]; const oldIndex = entries.findIndex(([key]) => key === draft.key);
    const rebuilt = new Map();
    entries.forEach(([key, value], index) => { if (index === oldIndex) rebuilt.set(newDraft.key, newDraft); if (key !== draft.key) rebuilt.set(key, value); });
    printerDrafts = rebuilt; activeDraftKey = newDraft.key;
    await refreshPrinterStatuses(); renderPrinterList(); renderPrinterEditor();
    $('printer-save-status').textContent = 'Printer saved.'; $('printer-save-status').dataset.state = 'ok'; setPageStatus(`${newDraft.printer.name} saved.`);
  } catch (error) {
    $('printer-save-status').textContent = error.message || 'Printer save failed.'; $('printer-save-status').dataset.state = 'error';
    draft.dirty = true; renderPrinterList(); $('save-printer').disabled = false;
  }
}
function discardPrinterDraft() {
  const draft = activeDraft(); if (!draft) return;
  if (draft.isNew) { printerDrafts.delete(draft.key); activeDraftKey = printerDrafts.keys().next().value || null; }
  else {
    const persisted = (runtimeConfig.printers || []).find((printer) => printer.id === draft.originalId);
    if (persisted) { const fresh = makeSavedDraft(persisted); fresh.key = draft.key; printerDrafts.set(draft.key, fresh); }
  }
  renderPrinterList(); renderPrinterEditor(); setPageStatus('Printer changes discarded.');
}
async function deletePrinterDraft() {
  const draft = activeDraft(); if (!draft) return;
  if (draft.isNew) return discardPrinterDraft();
  if ((runtimeConfig.printers || []).length <= 1) {
    $('printer-save-status').textContent = 'At least one printer must remain configured.'; $('printer-save-status').dataset.state = 'error'; return;
  }
  if (!window.confirm(`Delete ${draft.printer.name || draft.originalId}?`)) return;
  $('printer-save-status').textContent = 'Deleting printer…';
  const remaining = (runtimeConfig.printers || []).filter((printer) => printer.id !== draft.originalId);
  try {
    const systemResponse = await fetch('/api/system-config', {
      method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ printers: remaining })
    });
    const systemData = await systemResponse.json().catch(() => ({}));
    if (!systemResponse.ok) throw new Error(systemData.detail || 'Unable to delete printer.');
    runtimeConfig = systemData; printerDrafts.delete(draft.key); activeDraftKey = printerDrafts.keys().next().value || null;

    const overrides = { ...(overlaySettings.printer_overrides || {}) }; delete overrides[draft.originalId];
    const appearanceResponse = await fetch('/api/settings', {
      method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ ...overlaySettings, printer_overrides: overrides })
    });
    const appearanceData = await appearanceResponse.json().catch(() => ({}));
    let cleanupWarning = '';
    if (appearanceResponse.ok) overlaySettings = { ...APPEARANCE_DEFAULTS, ...appearanceData, printer_overrides: appearanceData.printer_overrides || {} };
    else cleanupWarning = ' The printer was deleted, but its unused overlay override could not be cleaned up.';
    await refreshPrinterStatuses(); renderPrinterList(); renderPrinterEditor(); setPageStatus(`Printer deleted.${cleanupWarning}`, !cleanupWarning);
  } catch (error) { $('printer-save-status').textContent = error.message || 'Unable to delete printer.'; $('printer-save-status').dataset.state = 'error'; }
}
async function testPrinterDraft() {
  const draft = activeDraft(); if (!draft) return;
  captureActiveDraft(false);
  const validationError = validatePrinterDraft(draft);
  if (validationError) { $('printer-connection-result').textContent = validationError; $('printer-connection-result').dataset.state = 'error'; return; }
  $('printer-connection-result').textContent = 'Testing connection…'; $('printer-connection-result').dataset.state = 'working';
  const response = await fetch('/api/printers/test', {
    method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ printer: printerForPersistence(draft.printer) })
  });
  const data = await response.json().catch(() => ({}));
  $('printer-connection-result').textContent = data.message || data.detail || (response.ok ? 'Connection successful.' : 'Connection failed.');
  $('printer-connection-result').dataset.state = response.ok ? 'ok' : 'error';
}
function hasDirtyPrinterDrafts() { return [...printerDrafts.values()].some((draft) => draft.dirty); }

window.renderPrintDirectorPrinterEditor = renderPrinterEditor;
window.renderPrintDirectorPrinterPreview = renderPrinterPreview;

document.querySelector('.printer-subnav').addEventListener('click', (event) => {
  const tab = event.target.closest('[data-printer-tab]'); if (tab) activatePrinterSection(tab.dataset.printerTab);
});
$('add-printer').addEventListener('click', addPrinterDraft);
$('save-printer').addEventListener('click', () => savePrinterDraft().catch((error) => { $('printer-save-status').textContent = error.message; $('printer-save-status').dataset.state = 'error'; }));
$('discard-printer-changes').addEventListener('click', discardPrinterDraft);
$('delete-printer').addEventListener('click', () => deletePrinterDraft().catch((error) => { $('printer-save-status').textContent = error.message; $('printer-save-status').dataset.state = 'error'; }));
$('test-printer').addEventListener('click', () => testPrinterDraft().catch((error) => { $('printer-connection-result').textContent = error.message; $('printer-connection-result').dataset.state = 'error'; }));
document.querySelectorAll('[data-printer-control]').forEach((control) => {
  const onChange = () => {
    if (suppressPrinterInput) return;
    const draft = activeDraft(); if (!draft) return;
    if (control.id === 'printer-custom-overlay' && control.checked) seedCustomOverlay(draft);
    captureActiveDraft(true);
    if (control.id === 'printer-type') updatePrinterTypeFields();
    if (control.id === 'printer-custom-overlay') updateCustomOverlayControls();
    renderPrinterPreview(); $('selected-printer-title').textContent = draft.printer.name || 'Unnamed printer';
    $('selected-printer-dirty').hidden = false; $('save-printer').disabled = false; $('discard-printer-changes').disabled = false; renderPrinterList();
  };
  control.addEventListener('input', onChange); control.addEventListener('change', onChange);
});
window.addEventListener('beforeunload', (event) => { if (hasDirtyPrinterDrafts()) { event.preventDefault(); event.returnValue = ''; } });
activatePrinterSection('connection');
window.printDirectorSettingsReady.then(() => initializePrinterDrafts()).catch(() => {});
