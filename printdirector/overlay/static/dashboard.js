const refreshLabel = document.getElementById('last-refresh');
const statusDot = document.querySelector('.status-dot');
const post = async (url) => {
  const response = await fetch(url, { method: 'POST', headers: authHeaders() });
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  refreshLabel.textContent = `Updated ${new Date().toLocaleTimeString()}`;
};

document.querySelectorAll('[data-show]').forEach((button) => {
  button.onclick = () => post(`/api/director/show/${button.dataset.show}`).catch(console.error);
});
document.querySelector('[data-action="return-auto"]').onclick = () => post('/api/director/return-auto').catch(console.error);
document.querySelectorAll('[data-stream]').forEach((button) => {
  button.onclick = () => post(`/api/stream/${button.dataset.stream}`).catch(console.error);
});

function setHealth(id, value, good = null) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = value;
  el.dataset.health = good === true ? 'good' : good === false ? 'bad' : 'neutral';
}

function applyHealth(data) {
  const preflight = data.obs_preflight || {};
  const ready = Boolean(preflight.ready);
  setHealth('health-obs-ready', ready ? 'READY' : (data.obs_connected ? 'DEGRADED' : 'OFFLINE'), ready);
  const missing = preflight.missing_scenes || [];
  document.getElementById('health-obs-detail').textContent = !data.obs_connected
    ? 'WebSocket unavailable'
    : !data.obs_preflight ? 'Preflight not run yet'
    : missing.length ? `Missing: ${missing.join(', ')}`
    : preflight.stream_service_configured === false ? 'Stream service not configured'
    : preflight.scene_collection_ok === false ? `Scene collection: ${preflight.scene_collection || '--'}`
    : preflight.profile_ok === false ? `Profile: ${preflight.profile || '--'}`
    : 'Scenes and stream service validated';

  const state = data.obs_stream_state || 'unknown';
  setHealth('health-stream', state.toUpperCase(), !['unknown','reconnecting'].includes(state));
  document.getElementById('health-stream-detail').textContent = `State age ${Math.round(Number(data.obs_stream_state_age || 0))}s`;

  const stale = data.stale_printers || [];
  setHealth('health-printers', `${data.online_printers ?? 0} / ${data.configured_printers ?? 0} fresh`, stale.length === 0);
  document.getElementById('health-stale').textContent = stale.length ? `Stale: ${stale.join(', ')}` : 'No stale telemetry';
  setHealth('health-notifications', data.notifications_enabled ? 'ENABLED' : 'OFF', null);

  statusDot.style.background = data.obs_connected ? (ready ? '#34d399' : '#fbbf24') : '#f87171';
}

function renderEvents(events) {
  const list = document.getElementById('event-list');
  if (!events || !events.length) {
    list.innerHTML = '<div class="event-empty">No events recorded yet.</div>';
    return;
  }
  list.replaceChildren(...events.map((event) => {
    const row = document.createElement('article');
    row.className = `event-row event-${event.severity || 'info'}`;
    const time = document.createElement('time');
    const date = new Date(event.timestamp);
    time.textContent = Number.isNaN(date.getTime()) ? '--:--:--' : date.toLocaleTimeString();
    const type = document.createElement('strong');
    type.textContent = String(event.type || 'event').replaceAll('_', ' ');
    const message = document.createElement('span');
    message.textContent = event.message || '';
    row.append(time, type, message);
    return row;
  }));
}

async function refreshOperations() {
  try {
    const [healthResponse, eventsResponse] = await Promise.all([
      fetch('/api/health', { headers: authHeaders() }),
      fetch('/api/events?limit=50', { headers: authHeaders() })
    ]);
    if (healthResponse.ok) applyHealth(await healthResponse.json());
    if (eventsResponse.ok) renderEvents(await eventsResponse.json());
    refreshLabel.textContent = `Live · ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    console.warn('Operational status refresh failed', error);
    statusDot.style.background = '#f87171';
  }
}

document.getElementById('download-diagnostics').addEventListener('click', async () => {
  try {
    const response = await fetch('/api/diagnostics', { headers: authHeaders() });
    if (!response.ok) throw new Error(`Diagnostics failed: ${response.status}`);
    const blob = await response.blob();
    const disposition = response.headers.get('Content-Disposition') || '';
    const match = disposition.match(/filename="?([^";]+)"?/i);
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = match?.[1] || 'printdirector-diagnostics.zip';
    link.click();
    URL.revokeObjectURL(link.href);
  } catch (error) {
    console.error(error);
  }
});

window.addEventListener('printdirector-update', (event) => {
  if (event.detail?.operations) applyHealth(event.detail.operations);
  if (event.detail?.events) renderEvents(event.detail.events);
});

refreshOperations();
setInterval(refreshOperations, 5000);
