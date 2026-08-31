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

const sampleData = [
  { printer_id: 'jotunn', printer_name: 'Jötunn', state: 'printing', filename: 'MyModel.gcode', progress: 0.62, estimated_remaining: 17 * 60, hotend_temperature: 205, hotend_target: 210, bed_temperature: 60, bed_target: 65, current_layer: 32, total_layers: 51, online: true },
  { printer_id: 'fenrir', printer_name: 'Fenrir', state: 'idle', filename: 'Ready for next print', progress: 0.15, estimated_remaining: null, hotend_temperature: 25, hotend_target: 30, bed_temperature: 25, bed_target: 30, current_layer: 0, total_layers: 0, online: true },
  { printer_id: 'wolf', printer_name: 'Wolf', state: 'offline', filename: 'Printer disconnected', progress: 0, estimated_remaining: null, hotend_temperature: null, hotend_target: null, bed_temperature: null, bed_target: null, current_layer: null, total_layers: null, online: false }
];

const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (m) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));
const fmt = (seconds) => seconds == null ? '--' : `${Math.floor(seconds / 3600)}:${String(Math.floor(seconds / 60) % 60).padStart(2, '0')}`;
const temp = (a, b) => `${a == null ? '--' : a.toFixed(0)}° / ${b == null ? '--' : b.toFixed(0)}°`;
const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

function getToken() {
  const value = localStorage.getItem('printdirector-token');
  if (!value) return null;
  return value.trim();
}

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function mergeSettings(base, specific = {}) {
  return { ...base, ...specific, printer_overrides: { ...(base.printer_overrides || {}), ...(specific.printer_overrides || {}) } };
}

function cardFor(printer, settings) {
  const merged = { ...defaults, ...settings, ...(settings.printer_overrides?.[printer.printer_id] || {}) };
  const progress = clamp(Number(printer.progress || 0), 0, 1);
  const name = escapeHtml(merged.label_override || printer.printer_name || 'Unknown printer');
  const state = escapeHtml(printer.state || 'offline');
  const file = escapeHtml(printer.filename || 'No active file');
  const eta = fmt(printer.estimated_remaining);
  const fontFamily = merged.font_family || defaults.font_family;
  const stateHtml = merged.show_state ? `<span class="state">${state}</span>` : '';
  const fileHtml = merged.show_filename ? `<div class="file">${file}</div>` : '';
  const etaHtml = merged.show_eta ? `<span>ETA ${eta}</span>` : '';
  const tempHtml = merged.show_temps ? `<div class="meta"><span>Hotend ${temp(printer.hotend_temperature, printer.hotend_target)}</span><span>Bed ${temp(printer.bed_temperature, printer.bed_target)}</span></div>` : '';
  const layerHtml = merged.show_layers && printer.current_layer ? `<div>Layer ${printer.current_layer} / ${printer.total_layers || '--'}</div>` : '';
  return `
    <section class="card" style="background: rgba(13,18,28,${merged.panel_opacity}); border-color: ${merged.accent_color}; color: ${merged.text_color}; font-family: ${fontFamily}; font-size: ${merged.font_scale.toFixed(2)}rem;">
      <div class="meta"><span class="label">${name}</span>${stateHtml}</div>
      ${fileHtml}
      <div class="bar"><i style="width:${(progress * 100).toFixed(2)}%; background:${merged.accent_color};"></i></div>
      <div class="meta"><span>${(progress * 100).toFixed(1)}%</span>${etaHtml}</div>
      ${tempHtml}
      ${layerHtml}
    </section>
  `;
}

async function loadSettings() {
  const response = await fetch('/api/settings', { headers: authHeaders() });
  if (!response.ok) {
    throw new Error('Unable to load preview settings');
  }
  const settings = await response.json();
  const layout = document.getElementById('preview');
  layout.innerHTML = sampleData.map((printer) => cardFor(printer, mergeSettings(defaults, settings))).join('');
  document.body.style.background = settings.theme === 'light' ? 'linear-gradient(180deg, rgba(148,163,184,0.12), #f8fafc)' : 'radial-gradient(circle at top, rgba(56,189,248,0.12), transparent 30%), #020817';
  document.body.style.color = settings.text_color || '#f5f7fa';
}

loadSettings().catch((error) => {
  const layout = document.getElementById('preview');
  layout.innerHTML = sampleData.map((printer) => cardFor(printer, defaults)).join('');
  console.warn(error);
});
